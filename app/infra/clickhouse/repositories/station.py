from app.dto.station import InsertObservation
from app.infra.clickhouse.repositories.base import ClickHouseRepository

_OBS_TABLE = "station_observations_raw"


class ClickStationRepository(ClickHouseRepository):
    async def insert_raw_observations(self, observations: list[InsertObservation]) -> None:
        if not observations:
            return

        ids = [obs.id for obs in observations]
        existing_result = await self._client.query(
            f"""
            SELECT observation_id
            FROM {_OBS_TABLE}
            WHERE observation_id IN ({",".join(str(obs_id) for obs_id in ids)})
            """
        )
        existing_ids = {row[0] for row in existing_result.result_rows}
        unique_observations = []
        seen_ids = set(existing_ids)
        for obs in observations:
            if obs.id in seen_ids:
                continue
            seen_ids.add(obs.id)
            unique_observations.append(obs)
        observations = unique_observations

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
