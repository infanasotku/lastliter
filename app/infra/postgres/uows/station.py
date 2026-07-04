from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.infra.postgres.repositories.station import PgStationRepository, PgStationWriteRepository
from app.infra.postgres.uows.base import PgReadUOWContext, PgUnitOfWork, PgWriteUOWContext


class StationReadContext(Protocol):
    stations: PgStationRepository


class StationWriteContext(Protocol):
    stations: PgStationWriteRepository


class PgStationReadContext(PgReadUOWContext):
    def __init__(self, *, session: AsyncSession):
        super().__init__(session=session)
        self.stations = PgStationRepository(session)


class PgStationWriteContext(PgWriteUOWContext):
    def __init__(self, *, session: AsyncSession, transaction: AsyncSessionTransaction):
        super().__init__(session=session, transaction=transaction)
        self.stations = PgStationWriteRepository(session)


class PgStationUnitOfWork(PgUnitOfWork[PgStationReadContext, PgStationWriteContext]):
    def _make_read_ctx(self, *, session: AsyncSession) -> PgStationReadContext:
        return PgStationReadContext(session=session)

    def _make_write_ctx(self, *, session: AsyncSession, transaction: AsyncSessionTransaction) -> PgStationWriteContext:
        return PgStationWriteContext(session=session, transaction=transaction)
