import hashlib
from datetime import timedelta
from itertools import chain

from app.contracts.uow import UnitOfWork
from app.domains.station import Station
from app.dto.station import (
    FetchRawStationObservations,
    InsertObservation,
    RawStationObservation,
    RunIngestionIterationCmd,
)
from app.infra.clickhouse.repositories import StationContext
from app.infra.common.time import now_utc
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging.logger import get_logger
from app.infra.postgres.uows import StationReadContext, StationWriteContext
from app.infra.redis.common import KEY_PREFIX
from app.infra.redis.limit import RateLimiter

ITERATION_BATCH_SIZE = 10
EVENTS_LIMIT_PER_STATION = 20
LIMIT_KEY = KEY_PREFIX + "stations:fetch:limit"
LIMIT_PER_SECOND = 2
CLAIM_FOR_SECONDS = 60 * 5  # 5 minutes

logger = get_logger().getChild(__name__)


class RunIngestionIterationUC:
    def __init__(
        self,
        uow: UnitOfWork[StationReadContext, StationWriteContext],
        *,
        click_ctx: StationContext,
        gdebenz: HTTPGdeBenzClient,
        limiter: RateLimiter,
    ):
        self._uow = uow
        self._gdebenz = gdebenz
        self._limiter = limiter
        self._click_ctx = click_ctx

    async def _claim_stations(self, owner: str) -> list[Station]:
        async with self._uow.begin(write=True) as ctx:
            stations = await ctx.stations.claim_stations(
                now=now_utc(),
                limit=ITERATION_BATCH_SIZE,
                owner=owner,
                claim_for=timedelta(seconds=CLAIM_FOR_SECONDS),
            )

        return stations

    async def _fetch_observations(self, stations: list[str]) -> dict[str, FetchRawStationObservations]:
        station_obs_dict: dict[str, FetchRawStationObservations] = {}

        for station_id in stations:
            try:
                await self._limiter.wait(key=LIMIT_KEY, limit_per_second=LIMIT_PER_SECOND)
                observations = await self._gdebenz.get_obs_by_id(station_id, limit=EVENTS_LIMIT_PER_STATION)

                station_obs_dict[station_id] = FetchRawStationObservations(
                    station_id=station_id, observations=observations
                )
            except Exception as e:
                logger.error(f"Failed to fetch observations for station {station_id}: {e}")

                station_obs_dict[station_id] = FetchRawStationObservations(
                    station_id=station_id, observations=[], error=str(e)
                )

        return station_obs_dict

    async def _process_failed_stations(
        self, stations: list[Station], obs: dict[str, FetchRawStationObservations], *, owner: str
    ) -> tuple[list[Station], dict[str, list[RawStationObservation]]]:
        failed_stations: list[Station] = []
        for station in stations:
            station_obs = obs[station.id]
            if station_obs.error:
                station.mark_fetch_error(now=now_utc(), error=station_obs.error)
                failed_stations.append(station)

        if not failed_stations:
            return stations, {k: v.observations for k, v in obs.items()}

        async with self._uow.begin(write=True) as ctx:
            await ctx.stations.update_claimed_stations(failed_stations, owner=owner)

        failed_ids = set(station.id for station in failed_stations)
        return [station for station in stations if station.id not in failed_ids], {
            k: v.observations for k, v in obs.items() if k not in failed_ids
        }

    async def _insert_observations(
        self, stations: list[Station], station_obs_dict: dict[str, list[RawStationObservation]]
    ) -> None:
        def _to_obs(raw: RawStationObservation, station: Station) -> InsertObservation:
            hash_target = f"{station.id}|{raw.created_at.isoformat()}|{raw.status}|{raw.detail}"
            ob_id = int(hashlib.md5(hash_target.encode()).hexdigest()[:16], 16)

            return InsertObservation(
                id=ob_id,
                status=raw.status,
                detail=raw.detail,
                created_at=raw.created_at,
                author_reliable=raw.author_reliable,
                on_site=raw.on_site,
                station_id=station.id,
            )

        # Just unwraps the list of lists into a single chain of observations
        obs_c = chain(*([_to_obs(o, station) for o in station_obs_dict[station.id]] for station in stations))
        obs = list(obs_c)

        error = None
        try:
            await self._click_ctx.stations.insert_raw_observations(obs)
        except Exception as e:
            logger.error(f"Failed to insert observations: {e}")
            error = str(e)

        for station in stations:
            if error:
                station.mark_fetch_error(now=now_utc(), error=error)
            else:
                station.update_fetch_info(now=now_utc(), observations_fetched=len(station_obs_dict[station.id]))

    async def run(self, cmd: RunIngestionIterationCmd) -> bool:
        stations = await self._claim_stations(owner=cmd.owner)
        if not stations:
            return False

        obs = await self._fetch_observations([station.id for station in stations])
        stations, obs = await self._process_failed_stations(stations, obs, owner=cmd.owner)

        await self._insert_observations(stations, obs)

        async with self._uow.begin(write=True) as ctx:
            await ctx.stations.update_claimed_stations(stations, owner=cmd.owner)

        return True
