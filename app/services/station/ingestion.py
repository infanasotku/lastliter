import asyncio
import contextlib
import hashlib
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from itertools import chain
from typing import AsyncGenerator

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
CLAIM_INTERVAL_SECONDS = 60  # 1 minute

logger = get_logger().getChild(__name__)


def _station_ids(stations: list[Station]) -> list[str]:
    return [station.id for station in stations]


class _HeartbeatStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class _HeartbeatContext:
    leased_stations: list[Station]

    status: _HeartbeatStatus
    error: str | None = None

    def retain_active(self, active_stations: list[Station]) -> None:
        ids = {station.id for station in active_stations}
        self.leased_stations = [station for station in self.leased_stations if station.id in ids]


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
        logger.info(
            f"Claiming up to {ITERATION_BATCH_SIZE} stations for owner {owner}",
            extra={
                "owner": owner,
                "limit": ITERATION_BATCH_SIZE,
                "claim_for_seconds": CLAIM_FOR_SECONDS,
            },
        )
        async with self._uow.begin(write=True) as ctx:
            stations = await ctx.stations.claim_stations(
                now=now_utc(),
                limit=ITERATION_BATCH_SIZE,
                owner=owner,
                claim_for=timedelta(seconds=CLAIM_FOR_SECONDS),
            )

        logger.info(
            f"Claimed {len(stations)} stations for owner {owner}",
            extra={
                "owner": owner,
                "stations_count": len(stations),
                "station_ids": _station_ids(stations),
            },
        )
        return stations

    @contextlib.asynccontextmanager
    async def _run_heartbeat_loop(
        self,
        stations: list[Station],
        *,
        owner: str,
    ) -> AsyncGenerator[_HeartbeatContext, None]:
        hb_ctx = _HeartbeatContext(
            leased_stations=stations,
            status=_HeartbeatStatus.RUNNING,
        )
        logger.info(
            f"Starting heartbeat loop for owner {owner} with {len(stations)} stations",
            extra={
                "owner": owner,
                "stations_count": len(stations),
                "station_ids": _station_ids(stations),
                "claim_for_seconds": CLAIM_FOR_SECONDS,
                "heartbeat_interval_seconds": CLAIM_INTERVAL_SECONDS,
            },
        )

        async def _wrap():
            try:
                await _loop()
            except Exception as e:
                logger.error(
                    f"Heartbeat loop: error occurred for owner {owner}: {e}",
                    extra={"owner": owner, "error": str(e)},
                )
                hb_ctx.status = _HeartbeatStatus.ERROR
                hb_ctx.error = str(e)

        async def _loop():
            while True:
                async with self._uow.begin(write=True) as ctx:
                    refreshed = await ctx.stations.refresh_lease(
                        hb_ctx.leased_stations,
                        owner=owner,
                        claim_for=timedelta(seconds=CLAIM_FOR_SECONDS),
                        now=now_utc(),
                    )

                    if not refreshed:
                        logger.warning(
                            f"Heartbeat loop: no stations refreshed for owner {owner}, stopping loop",
                            extra={
                                "owner": owner,
                                "stations_count": len(hb_ctx.leased_stations),
                                "station_ids": _station_ids(hb_ctx.leased_stations),
                            },
                        )
                        hb_ctx.leased_stations = []
                        break
                    if refreshed != len(hb_ctx.leased_stations):
                        logger.warning(
                            f"Heartbeat loop: refreshed {refreshed} out of {len(hb_ctx.leased_stations)} stations for owner {owner}",
                            extra={
                                "owner": owner,
                                "refreshed_count": refreshed,
                                "stations_count": len(hb_ctx.leased_stations),
                                "station_ids": _station_ids(hb_ctx.leased_stations),
                            },
                        )
                        hb_ctx.leased_stations = await ctx.stations.get_claimed(owner=owner, now=now_utc())
                        logger.info(
                            f"Heartbeat loop: retained {len(hb_ctx.leased_stations)} claimed stations for owner {owner}",
                            extra={
                                "owner": owner,
                                "stations_count": len(hb_ctx.leased_stations),
                                "station_ids": _station_ids(hb_ctx.leased_stations),
                            },
                        )

                await asyncio.sleep(CLAIM_INTERVAL_SECONDS)

        task = asyncio.create_task(_wrap())

        try:
            yield hb_ctx
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

            hb_ctx.status = _HeartbeatStatus.COMPLETED
            logger.info(
                f"Heartbeat loop stopped for owner {owner}",
                extra={
                    "owner": owner,
                    "stations_count": len(hb_ctx.leased_stations),
                    "station_ids": _station_ids(hb_ctx.leased_stations),
                },
            )

    async def _fetch_observations(self, stations: list[str]) -> dict[str, FetchRawStationObservations]:
        station_obs_dict: dict[str, FetchRawStationObservations] = {}
        logger.info(
            f"Fetching observations for {len(stations)} stations",
            extra={"stations_count": len(stations), "station_ids": stations},
        )

        for station_id in stations:
            try:
                await self._limiter.wait(key=LIMIT_KEY, limit_per_second=LIMIT_PER_SECOND)
                observations = await self._gdebenz.get_obs_by_id(station_id, limit=EVENTS_LIMIT_PER_STATION)

                station_obs_dict[station_id] = FetchRawStationObservations(
                    station_id=station_id, observations=observations
                )
                logger.info(
                    f"Fetched {len(observations)} observations for station {station_id}",
                    extra={
                        "station_id": station_id,
                        "observations_count": len(observations),
                        "events_limit": EVENTS_LIMIT_PER_STATION,
                    },
                )
            except Exception as e:
                logger.error(
                    f"Failed to fetch observations for station {station_id}: {e}",
                    extra={"station_id": station_id, "error": str(e)},
                )

                station_obs_dict[station_id] = FetchRawStationObservations(
                    station_id=station_id, observations=[], error=str(e)
                )

        failed_count = sum(1 for station_obs in station_obs_dict.values() if station_obs.error)
        observations_count = sum(len(station_obs.observations) for station_obs in station_obs_dict.values())
        logger.info(
            f"Finished fetching observations: {observations_count} observations, {failed_count} failed stations",
            extra={
                "stations_count": len(stations),
                "observations_count": observations_count,
                "failed_stations_count": failed_count,
            },
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
            logger.info(
                f"No station fetch failures for owner {owner}",
                extra={"owner": owner, "stations_count": len(stations), "station_ids": _station_ids(stations)},
            )
            return stations, {k: v.observations for k, v in obs.items()}

        logger.warning(
            f"Marking {len(failed_stations)} stations as failed for owner {owner}",
            extra={
                "owner": owner,
                "failed_stations_count": len(failed_stations),
                "failed_station_ids": _station_ids(failed_stations),
            },
        )
        async with self._uow.begin(write=True) as ctx:
            await ctx.stations.update_claimed_stations(
                failed_stations,  # update filters not claimed stations by it's own
                owner=owner,
                now=now_utc(),
            )

        failed_ids = set(station.id for station in failed_stations)
        active_stations = [station for station in stations if station.id not in failed_ids]
        logger.info(
            f"Continuing ingestion with {len(active_stations)} active stations for owner {owner}",
            extra={
                "owner": owner,
                "stations_count": len(active_stations),
                "station_ids": _station_ids(active_stations),
            },
        )
        return active_stations, {k: v.observations for k, v in obs.items() if k not in failed_ids}

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
        logger.info(
            f"Inserting {len(obs)} observations for {len(stations)} stations into ClickHouse",
            extra={
                "observations_count": len(obs),
                "stations_count": len(stations),
                "station_ids": _station_ids(stations),
            },
        )

        stations_error_dict: dict[str, str] = {}
        try:
            await self._click_ctx.stations.insert_raw_observations(obs)
            logger.info(
                f"Bulk inserted {len(obs)} observations into ClickHouse",
                extra={"observations_count": len(obs)},
            )
        except Exception as e:
            logger.error(
                f"Failed to bulk insert {len(obs)} observations: {e}, trying to insert one by one",
                extra={"observations_count": len(obs), "error": str(e)},
            )
            for ob in obs:
                try:
                    await self._click_ctx.stations.insert_raw_observations([ob])
                except Exception as e:
                    logger.error(
                        f"Failed to insert observation {ob.id}: {e}",
                        extra={"observation_id": ob.id, "station_id": ob.station_id, "error": str(e)},
                    )
                    stations_error_dict[ob.station_id] = str(e)

        for station in stations:
            if station.id in stations_error_dict:
                station.mark_fetch_error(now=now_utc(), error=stations_error_dict[station.id])
            else:
                station.update_fetch_info(now=now_utc(), observations_fetched=len(station_obs_dict[station.id]))
        logger.info(
            f"Prepared station feedback after ClickHouse insert: {len(stations_error_dict)} stations failed",
            extra={
                "stations_count": len(stations),
                "failed_stations_count": len(stations_error_dict),
                "failed_station_ids": list(stations_error_dict),
            },
        )

    async def run(self, cmd: RunIngestionIterationCmd) -> bool:
        logger.info(f"Starting ingestion iteration for owner {cmd.owner}", extra={"owner": cmd.owner})
        stations = await self._claim_stations(owner=cmd.owner)
        if not stations:
            logger.info(f"Ingestion iteration has no work for owner {cmd.owner}", extra={"owner": cmd.owner})
            return False

        async with self._run_heartbeat_loop(stations, owner=cmd.owner) as hb_ctx:
            obs = await self._fetch_observations([station.id for station in stations])
            stations, obs = await self._process_failed_stations(stations, obs, owner=cmd.owner)
            hb_ctx.retain_active(stations)
            logger.info(
                f"Retained {len(hb_ctx.leased_stations)} leased stations after fetch processing for owner {cmd.owner}",
                extra={
                    "owner": cmd.owner,
                    "stations_count": len(hb_ctx.leased_stations),
                    "station_ids": _station_ids(hb_ctx.leased_stations),
                },
            )

            if hb_ctx.status == _HeartbeatStatus.ERROR:
                logger.error(
                    f"Heartbeat loop encountered an error for owner {cmd.owner}: {hb_ctx.error}",
                    extra={"owner": cmd.owner, "error": hb_ctx.error},
                )
                return False
            if not hb_ctx.leased_stations:
                logger.warning(
                    f"No leased stations left for owner {cmd.owner}, stopping ingestion iteration",
                    extra={"owner": cmd.owner},
                )
                return False

            await self._insert_observations(hb_ctx.leased_stations, obs)

            logger.info(
                f"Updating ingestion feedback for {len(stations)} stations owned by {cmd.owner}",
                extra={"owner": cmd.owner, "stations_count": len(stations), "station_ids": _station_ids(stations)},
            )
            async with self._uow.begin(write=True) as ctx:
                await ctx.stations.update_claimed_stations(
                    stations,  # update filters not claimed stations by it's own
                    owner=cmd.owner,
                    now=now_utc(),
                )
            logger.info(
                f"Ingestion feedback updated for {len(stations)} stations owned by {cmd.owner}",
                extra={"owner": cmd.owner, "stations_count": len(stations), "station_ids": _station_ids(stations)},
            )

        logger.info(f"Ingestion iteration completed for owner {cmd.owner}", extra={"owner": cmd.owner})
        return True
