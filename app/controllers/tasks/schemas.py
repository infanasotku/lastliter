from pydantic import BaseModel, Field

from app.dto.station import AddStationsByAreaFilters


class AddStationsByAreaRequest(BaseModel):
    lat1: float
    lon1: float
    lat2: float
    lon2: float
    filters: AddStationsByAreaFilters = Field(default_factory=AddStationsByAreaFilters)


class AddStationBySharedLinkRequest(BaseModel):
    shared_link: str
