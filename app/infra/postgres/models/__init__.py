# Hack for Base.metadata to be available in env.py
# for autogenerate support
from app.infra.postgres.models import ingestion, station

__all__ = ["station", "ingestion"]
