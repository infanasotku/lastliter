from sqlalchemy.ext.asyncio import AsyncSession


class PostgresRepository:
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session
