from app.dto.station import InsertObservation
from app.infra.clickhouse.repositories.base import ClickHouseRepository


class ClickStationRepository(ClickHouseRepository):
    async def insert_raw_observations(self, observations: list[InsertObservation]) -> None:
        if not observations:
            return

        stmt = """
"""

        await self._client.command(stmt)
