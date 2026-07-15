from datetime import datetime, timedelta

from sqlalchemy import literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.domains.state import IngestionPipelineState
from app.infra.postgres.models.ingestion import IngestionPipelineState as IngestionPipelineStateModel
from app.infra.postgres.repositories.base import PostgresRepository


def _to_domain(model: IngestionPipelineStateModel) -> IngestionPipelineState:
    return IngestionPipelineState(
        station_id=model.station_id,
        pipeline_type=model.pipeline_type,
        last_processed_at=model.last_processed_at,
        next_run_at=model.next_run_at,
        interval_sec=model.interval_sec,
        error=model.error,
        priority=model.priority,
        claimed_by=model.claimed_by,
        lease_until=model.lease_until,
        meta=model.meta,
    )


class PgIngestionStateRepository(PostgresRepository):
    pass


class PgIngestionStateWriteRepository(PgIngestionStateRepository):
    async def claim_states(
        self,
        *,
        now: datetime,
        limit: int,
        owner: str,
        claim_for: timedelta,
        pipeline_type: str,
    ) -> list[IngestionPipelineState]:
        picked = (
            select(IngestionPipelineStateModel.station_id)
            .where(
                IngestionPipelineStateModel.next_run_at <= now,
                or_(
                    IngestionPipelineStateModel.lease_until.is_(None),
                    IngestionPipelineStateModel.lease_until <= now,
                ),
                IngestionPipelineStateModel.pipeline_type == pipeline_type,
            )
            .order_by(
                IngestionPipelineStateModel.priority.desc(),
                IngestionPipelineStateModel.last_processed_at.asc(),
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
            .cte("picked")
        )

        stmt = (
            update(IngestionPipelineStateModel)
            .where(
                IngestionPipelineStateModel.station_id.in_(select(picked.c.station_id)),
                IngestionPipelineStateModel.pipeline_type == pipeline_type,
            )
            .values(claimed_by=owner, lease_until=now + claim_for)
            .returning(IngestionPipelineStateModel)
        )

        states = await self._session.scalars(stmt)
        return [_to_domain(state) for state in states]

    async def refresh_lease(
        self,
        states: list[IngestionPipelineState],
        *,
        owner: str,
        claim_for: timedelta,
        now: datetime,
        pipeline_type: str,
    ) -> int:
        stmt = (
            update(IngestionPipelineStateModel)
            .where(
                IngestionPipelineStateModel.station_id.in_({s.station_id for s in states}),
                IngestionPipelineStateModel.claimed_by == owner,
                IngestionPipelineStateModel.lease_until > now,
                IngestionPipelineStateModel.pipeline_type == pipeline_type,
            )
            .values(lease_until=now + claim_for)
            .returning(literal(1))
        )
        updated = await self._session.scalars(stmt)

        return len(list(updated))

    async def update_claimed_states(
        self,
        states: list[IngestionPipelineState],
        *,
        owner: str,
        now: datetime,
        pipeline_type: str,
    ) -> int:
        if not states:
            return 0

        updated = 0

        for state in states:
            stmt = (
                update(IngestionPipelineStateModel)
                .where(
                    IngestionPipelineStateModel.station_id == state.station_id,
                    IngestionPipelineStateModel.claimed_by == owner,
                    IngestionPipelineStateModel.lease_until > now,
                    IngestionPipelineStateModel.pipeline_type == pipeline_type,
                )
                .values(
                    last_processed_at=state.last_processed_at,
                    next_run_at=state.next_run_at,
                    interval_sec=state.interval_sec,
                    error=state.error,
                    lease_until=None,
                    claimed_by=None,
                )
                .returning(literal(1))
            )
            result = await self._session.scalar(stmt)
            updated += 1 if result is not None else 0

        return updated

    async def get_claimed(self, owner: str, now: datetime, pipeline_type: str) -> list[IngestionPipelineState]:
        stmt = select(IngestionPipelineStateModel).where(
            IngestionPipelineStateModel.claimed_by == owner,
            IngestionPipelineStateModel.lease_until > now,
            IngestionPipelineStateModel.pipeline_type == pipeline_type,
        )
        states = await self._session.scalars(stmt)
        return [_to_domain(state) for state in states]

    async def insert_many_safe(self, states: list[IngestionPipelineState]) -> int:
        if not states:
            return 0

        vals = [
            {
                "station_id": s.station_id,
                "pipeline_type": s.pipeline_type,
                #
                "last_processed_at": s.last_processed_at,
                "next_run_at": s.next_run_at,
                "interval_sec": s.interval_sec,
                "error": s.error,
                "priority": s.priority,
                #
                "claimed_by": s.claimed_by,
                "lease_until": s.lease_until,
                #
                "meta": s.meta,
            }
            for s in states
        ]

        stmt = (
            pg_insert(IngestionPipelineStateModel)
            .values(vals)
            .on_conflict_do_nothing(
                index_elements=[IngestionPipelineStateModel.station_id, IngestionPipelineStateModel.pipeline_type]
            )
            .returning(literal(1))
        )
        inserted = await self._session.scalars(stmt)
        return len(list(inserted))
