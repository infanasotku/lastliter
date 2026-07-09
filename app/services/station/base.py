from typing import Protocol

from app.contracts.uow import UnitOfWork
from app.infra.clickhouse.repositories import StationContext
from app.infra.http.gdebenz import HTTPGdeBenzClient
from app.infra.postgres.uows import StationReadContext, StationWriteContext
from app.infra.redis.limit import RateLimiter


class StationServiceDeps(Protocol):
    _uow: UnitOfWork[StationReadContext, StationWriteContext]
    _gdebenz: HTTPGdeBenzClient
    _limiter: RateLimiter
    _click_ctx: StationContext
