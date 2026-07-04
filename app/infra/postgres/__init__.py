from sqlalchemy.ext.asyncio import create_async_engine

from app.infra.config.postgres import PostgreSQLSettings


def create_engine(settings: PostgreSQLSettings, *, tx: bool = False):
    return create_async_engine(
        str(settings.dsn),
        pool_pre_ping=False,
        pool_recycle=3600,
        pool_size=20,
        isolation_level="AUTOCOMMIT" if not tx else None,
    )
