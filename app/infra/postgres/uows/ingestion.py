from typing import Protocol

from app.infra.postgres.repositories.state import PgIngestionStateRepository, PgIngestionStateWriteRepository


class IngestionReadContext(Protocol):
    states: PgIngestionStateRepository


class IngestionWriteContext(Protocol):
    states: PgIngestionStateWriteRepository
