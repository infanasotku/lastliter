import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import (
    AsyncIterator,
    TypeVar,
)

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncSessionTransaction,
    async_sessionmaker,
)

from app.infra.logging.logger import get_logger

logger = get_logger().getChild(__name__)


class PgReadUOWContext:
    def __init__(self, *, session: AsyncSession):
        self._session = session


class PgWriteUOWContext(PgReadUOWContext):
    def __init__(self, *, session: AsyncSession, transaction: AsyncSessionTransaction):
        super().__init__(session=session)
        self._transaction = transaction


ReadContextT = TypeVar("ReadContextT", bound=PgReadUOWContext, covariant=True)
WriteContextT = TypeVar("WriteContextT", bound=PgWriteUOWContext, covariant=True)


class PgUnitOfWork[ReadContextT: PgReadUOWContext, WriteContextT: PgWriteUOWContext](ABC):
    def __init__(
        self,
        *,
        read_sessionmaker: async_sessionmaker[AsyncSession],
        write_sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        self._read_sessionmaker = read_sessionmaker
        self._write_sessionmaker = write_sessionmaker

    @abstractmethod
    def _make_write_ctx(self, *, session: AsyncSession, transaction: AsyncSessionTransaction) -> WriteContextT: ...
    @abstractmethod
    def _make_read_ctx(self, *, session: AsyncSession) -> ReadContextT: ...

    async def _start(self, *, write: bool) -> WriteContextT | ReadContextT:
        if write:
            logger.debug("Opening write unit of work with transaction")
            session = self._write_sessionmaker()
            transaction = await session.begin()
            return self._make_write_ctx(session=session, transaction=transaction)
        else:
            logger.debug("Opening read unit of work without transaction")
            session = self._read_sessionmaker()
            return self._make_read_ctx(session=session)

    async def _finish(
        self,
        exc: BaseException | None,
        *,
        ctx: WriteContextT | ReadContextT,
    ):
        try:
            if exc is None:
                if isinstance(ctx, PgWriteUOWContext):
                    logger.debug("Committing unit of work transaction")
                    await ctx._transaction.commit()
            else:
                raise exc
        except BaseException:
            if isinstance(ctx, PgWriteUOWContext):
                try:
                    logger.warning("Rolling back unit of work transaction")
                    await ctx._session.rollback()
                except Exception:
                    pass
            raise
        finally:
            logger.debug("Closing unit of work session")
            await ctx._session.close()

    @asynccontextmanager
    async def begin(self, *, write: bool) -> AsyncIterator[WriteContextT | ReadContextT]:
        ctx = await self._start(write=write)
        try:
            yield ctx
        except BaseException as ex:  # With CancelledError
            await asyncio.shield(self._finish(ex, ctx=ctx))
        else:
            await asyncio.shield(self._finish(None, ctx=ctx))
