from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import literal, or_, select, update
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
        last_fetched_at=model.last_fetched_at,
        next_fetch_at=model.next_fetch_at,
        fetch_interval_sec=model.fetch_interval_sec,
        priority=model.priority,
    )


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
                "last_fetched_at": station.last_fetched_at,
                "next_fetch_at": station.next_fetch_at,
                "fetch_interval_sec": station.fetch_interval_sec,
                "priority": station.priority,
                "lease_until": None,
                "claimed_by": None,
            }
            for station in stations
        ]

        stmt = pg_insert(StationModel).values(vals).on_conflict_do_nothing(index_elements=["id"]).returning(literal(1))
        inserted = await self._session.scalars(stmt)
        return len(list(inserted))

    async def claim_stations(
        self,
        *,
        now: datetime,
        limit: int,
        owner: str,
        claim_for: timedelta,
    ) -> list[Station]:
        picked = (
            select(StationModel.id)
            .where(
                StationModel.next_fetch_at <= now,
                or_(
                    StationModel.lease_until.is_(None),
                    StationModel.lease_until <= now,
                ),
            )
            .order_by(
                StationModel.priority.desc(),
                StationModel.last_fetched_at.asc(),
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
            .cte("picked")
        )

        stmt = (
            update(StationModel)
            .where(StationModel.id == picked.c.id)
            .values(
                lease_until=now + claim_for,
                claimed_by=owner,
            )
            .returning(StationModel)
        )

        stations = await self._session.scalars(stmt)
        return [_to_domain(station) for station in stations]

    async def update_claimed_stations(
        self,
        stations: Sequence[Station],
        *,
        owner: str,
    ) -> int:
        if not stations:
            return 0

        updated = 0

        for station in stations:
            stmt = (
                update(StationModel)
                .where(
                    StationModel.id == station.id,
                    StationModel.claimed_by == owner,
                )
                .values(
                    last_fetched_at=station.last_fetched_at,
                    next_fetch_at=station.next_fetch_at,
                    fetch_interval_sec=station.fetch_interval_sec,
                    lease_until=None,
                    claimed_by=None,
                )
                .returning(literal(1))
            )
            result = await self._session.scalar(stmt)
            updated += 1 if result is not None else 0

        return updated
