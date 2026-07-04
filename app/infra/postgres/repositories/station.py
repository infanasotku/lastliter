from collections.abc import Sequence

from sqlalchemy import literal
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.domains.station import Station
from app.infra.logging.logger import logger as base_logger
from app.infra.postgres.models.station import Station as StationModel
from app.infra.postgres.repositories.base import PostgresRepository

logger = base_logger.getChild(__name__)


class PgStationRepository(PostgresRepository):
    pass


class PgStationWriteRepository(PgStationRepository):
    async def insert_many_safe(self, stations: Sequence[Station]) -> int:
        if not stations:
            return 0

        vals = [
            {
                "id": station.id,
                "name": station.name,
                "address": station.address,
                "lat": station.lat,
                "lon": station.lon,
            }
            for station in stations
        ]

        stmt = pg_insert(StationModel).values(vals).on_conflict_do_nothing(index_elements=["id"]).returning(literal(1))
        inserted = await self._session.scalars(stmt)
        return len(list(inserted))
