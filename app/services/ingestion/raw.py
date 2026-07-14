import hashlib
from itertools import chain

from app.domains.station import Station
from app.dto.ingestion import (
    FetchRawStationObservations,
    InsertObservation,
    RawStationObservation,
    RunIngestionIterationCmd,
)
from app.infra.clickhouse.repositories import StationContext
from app.infra.common.time import now_utc
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging.logger import get_logger
from app.infra.redis.common import KEY_PREFIX
from app.infra.redis.limit import RateLimiter
from app.services.ingestion.base import _HeartbeatContext, _IngestionIterationUC, _station_ids

logger = get_logger().getChild(__name__)

LIMIT_KEY = KEY_PREFIX + "stations:fetch:limit"
LIMIT_PER_SECOND = 2
EVENTS_LIMIT_PER_STATION = 20


class FetchRawObservationsUC(_IngestionIterationUC):
    def __init__(
        self,
        cmd: RunIngestionIterationCmd,
        *,
        hb_ctx: _HeartbeatContext,
        click_ctx: StationContext,
        gdebenz: HTTPGdeBenzClient,
        limiter: RateLimiter,
    ):
        self.cmd = cmd

        self._gdebenz = gdebenz
        self._limiter = limiter
        self._click_ctx = click_ctx

        self._hb_ctx = hb_ctx

    async def _fetch_observations(self, stations: list[Station]) -> dict[str, FetchRawStationObservations]:
        station_obs_dict: dict[str, FetchRawStationObservations] = {}
        logger.info(
            f"Fetching observations for {len(stations)} stations",
            extra={"stations_count": len(stations), "station_ids": _station_ids(stations)},
        )

        for station in stations:
            try:
                await self._limiter.wait(key=LIMIT_KEY, limit_per_second=LIMIT_PER_SECOND)
                observations = await self._gdebenz.get_obs_by_id(station.id, limit=EVENTS_LIMIT_PER_STATION)

                station_obs_dict[station.id] = FetchRawStationObservations(observations=observations)
                logger.info(
                    f"Fetched {len(observations)} observations for station {station.id}",
                    extra={
                        "station_id": station.id,
                        "observations_count": len(observations),
                        "events_limit": EVENTS_LIMIT_PER_STATION,
                    },
                )
            except Exception as e:
                logger.error(
                    f"Failed to fetch observations for station {station.id}: {e}",
                    extra={"station_id": station.id, "error": str(e)},
                )

                station.mark_process_error(now=now_utc(), error=str(e))

        failed_count = sum(1 for s in stations if s.fetch_error)
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

    async def _insert_observations(
        self, stations: list[Station], station_obs_dict: dict[str, FetchRawStationObservations]
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
        obs_c = chain(
            *([_to_obs(o, station) for o in station_obs_dict[station.id].observations] for station in stations)
        )
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
                station.mark_process_error(now=now_utc(), error=stations_error_dict[station.id])
            else:
                station.update_process_info(
                    now=now_utc(), observations_fetched=len(station_obs_dict[station.id].observations)
                )
        logger.info(
            f"Prepared station feedback after ClickHouse insert: {len(stations_error_dict)} stations failed",
            extra={
                "stations_count": len(stations),
                "failed_stations_count": len(stations_error_dict),
                "failed_station_ids": list(stations_error_dict),
            },
        )

    async def run(self, stations: list[Station]) -> None:
        obs = await self._fetch_observations(stations)
        self._hb_ctx.retain_active([s for s in stations if not s.fetch_error])
        logger.info(
            f"Retained {len(self._hb_ctx.leased_stations)} leased stations after fetch processing for owner {self.cmd.owner}",
            extra={
                "owner": self.cmd.owner,
                "stations_count": len(self._hb_ctx.leased_stations),
                "station_ids": _station_ids(self._hb_ctx.leased_stations),
            },
        )

        if self._hb_ctx.exhausted:
            return

        await self._insert_observations(self._hb_ctx.leased_stations, obs)
