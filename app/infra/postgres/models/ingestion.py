from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domains.state import PipelineType
from app.infra.postgres.models.base import Base


class IngestionPipelineState(Base):
    __tablename__ = "ingestion_pipeline_states"

    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"))
    pipeline_type: Mapped[PipelineType] = mapped_column(String)

    last_processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_sec: Mapped[int] = mapped_column(nullable=False)
    error: Mapped[str | None] = mapped_column(nullable=True)
    priority: Mapped[int] = mapped_column(nullable=False)

    claimed_by: Mapped[str | None] = mapped_column(nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    meta: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint(
            "station_id",
            "pipeline_type",
            name="ingestion_pipeline_states_pk",
        ),
    )
