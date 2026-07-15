from app.contracts.uow import UnitOfWork
from app.dto.ingestion import RunIngestionIterationCmd
from app.infra.clickhouse.repositories import StationContext
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.logging import get_logger
from app.infra.postgres.uows import IngestionReadContext, IngestionWriteContext
from app.infra.redis.limit import RateLimiter

logger = get_logger().getChild(__name__)


class IngestionService:
    def __init__(
        self,
        uow: UnitOfWork[IngestionReadContext, IngestionWriteContext],
        *,
        click_ctx: StationContext,
        gdebenz: HTTPGdeBenzClient,
        limiter: RateLimiter,
    ) -> None:
        self._uow = uow
        self._gdebenz = gdebenz
        self._limiter = limiter
        self._click_ctx = click_ctx

    async def run_ingestion_iteration(self, cmd: RunIngestionIterationCmd) -> bool:
        from app.services.ingestion.iter import RunIngestionIterationUC

        return await RunIngestionIterationUC(
            cmd,
            uow=self._uow,
            click_ctx=self._click_ctx,
            gdebenz=self._gdebenz,
            limiter=self._limiter,
        ).run()
