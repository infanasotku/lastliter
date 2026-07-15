from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.domains.station import Station
from app.infra.logging.logger import logger as base_logger
from app.infra.postgres.models.station import Station as StationModel
from app.infra.postgres.repositories.base import PostgresRepository

logger = base_logger.getChild(__name__)


def _to_domain(model: StationModel) -> Station:
    return Station(
        id=model.id,
        name=model.name,
        address=model.address,
        lat=model.lat,
        lon=model.lon,
    )


class PgStationRepository(PostgresRepository):
    async def get_by_id(self, id: str) -> Station | None:
        stmt = select(StationModel).where(StationModel.id == id)
        station = await self._session.scalar(stmt)
        return _to_domain(station) if station else None


class PgStationWriteRepository(PgStationRepository):
    async def insert_many_safe(self, stations: Sequence[Station]) -> list[Station]:
        if not stations:
            return []

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

        stmt = (
            pg_insert(StationModel)
            .values(vals)
            .on_conflict_do_nothing(index_elements=[StationModel.id])
            .returning(StationModel)
        )
        inserted = await self._session.scalars(stmt)
        return [_to_domain(station) for station in inserted]
