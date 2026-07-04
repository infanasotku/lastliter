from sqlalchemy.orm import Mapped, mapped_column

from app.infra.postgres.models.base import Base, strpk


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[strpk]

    name: Mapped[str] = mapped_column(nullable=False)
    address: Mapped[str] = mapped_column(nullable=False)

    lat: Mapped[float] = mapped_column(nullable=False)
    lon: Mapped[float] = mapped_column(nullable=False)
