import hashlib
from itertools import chain

from app.contracts.uow import UnitOfWork
from app.domains.station import Station
from app.dto.station import (
    InsertObservation,
    RawStationObservation,
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

    async def _fetch_observations(self, stations: list[Station]) -> dict[str, list[RawStationObservation]]:
        station_obs_dict: dict[str, list[RawStationObservation]] = {}

        for station in stations:
            await self._limiter.wait(key=LIMIT_KEY, limit_per_second=LIMIT_PER_SECOND)
            station_obs_dict[station.id] = await self._gdebenz.get_obs_by_id(station.id, limit=EVENTS_LIMIT_PER_STATION)

        return station_obs_dict

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
        obs_c = chain(*([_to_obs(o, station) for o in station_obs_dict.get(station.id, [])] for station in stations))
        obs = list(obs_c)
        await self._click_ctx.stations.insert_raw_observations(obs)

        for station in stations:
            obs = station_obs_dict.get(station.id, [])
            station.update_fetch_info(now=now_utc(), observations_fetched=len(obs))

    async def run(self):
        async with self._uow.begin(write=True) as ctx:
            stations = await ctx.stations.get_stations_for_fetch_for_update(
                now=now_utc(),
                limit=ITERATION_BATCH_SIZE,
            )
            if not stations:
                return False

            obs = await self._fetch_observations(stations)
            await self._insert_observations(stations, obs)

            await ctx.stations.update_stations(stations)
            return True
