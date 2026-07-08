from app.dto.station import InsertObservation
from app.infra.clickhouse.repositories.base import ClickHouseRepository

_OBS_TABLE = "station_observations_raw"


class ClickStationRepository(ClickHouseRepository):
    async def insert_raw_observations(self, observations: list[InsertObservation]) -> None:
        if not observations:
            return

        rows = [
            (
                obs.id,
                obs.station_id,
                obs.created_at,
                obs.status,
                obs.detail,
                obs.author_reliable,
                obs.on_site,
            )
            for obs in observations
        ]

        await self._client.insert(
            _OBS_TABLE,
            data=rows,
            column_names=[
                "observation_id",
                "station_id",
                "observed_at",
                "status",
                "detail",
                "author_reliable",
                "on_site",
            ],
        )
