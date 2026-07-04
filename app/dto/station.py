from pydantic import BaseModel


class SyncStationCmd(BaseModel):
    lat1: float
    lon1: float

    lat2: float
    lon2: float


class StartSyncStationCmd(SyncStationCmd):
    correlation_id: str


class SyncStationResult(BaseModel):
    new: int
