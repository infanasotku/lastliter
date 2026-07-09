from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.postgres.models.base import Base, strpk


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[strpk]

    name: Mapped[str] = mapped_column(nullable=False)
    address: Mapped[str] = mapped_column(nullable=False)

    lat: Mapped[float] = mapped_column(nullable=False)
    lon: Mapped[float] = mapped_column(nullable=False)

    last_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_fetch_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetch_interval_sec: Mapped[int] = mapped_column(nullable=False)
    fetch_error: Mapped[str | None] = mapped_column(nullable=True)
    priority: Mapped[int] = mapped_column(nullable=False)

    claimed_by: Mapped[str | None] = mapped_column(nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
