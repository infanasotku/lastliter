from app.infra.logging.logger import logger as base_logger
from app.infra.postgres.repositories.base import PostgresRepository

logger = base_logger.getChild(__name__)


class PgStationRepository(PostgresRepository):
    pass


class PgStationWriteRepository(PgStationRepository):
    pass
