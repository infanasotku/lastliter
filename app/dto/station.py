from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from app.domains.station import Station


class StationDTO(BaseModel):
    id: str

    name: str
    address: str

    lat: float
    lon: float

    score: float | None = None
    confidence: float | None = None

    @classmethod
    def from_domain(cls, station: Station) -> Self:
        return cls(
            id=station.id,
            name=station.name,
            address=station.address,
            lat=station.lat,
            lon=station.lon,
        )


class AddStationsByAreaFilters(BaseModel):
    by_name: str | None = None
    by_id: str | None = None


class AddStationsByAreaCmd(BaseModel):
    lat1: float
    lon1: float

    lat2: float
    lon2: float

    filters: AddStationsByAreaFilters = Field(default_factory=AddStationsByAreaFilters)


class StartAddStationsByAreaCmd(AddStationsByAreaCmd):
    correlation_id: str


class AddStationsByAreaResult(BaseModel):
    inserted_count: int


class AddStationBySharedLinkCmd(BaseModel):
    shared_link: str


class StartAddStationBySharedLinkCmd(AddStationBySharedLinkCmd):
    correlation_id: str


class StationHourlyStats(BaseModel):
    hour: int
    weekday: int

    observations_count: int

    fuel_available_ratio: float | None
    queue_probability_when_known: float | None
    queue_data_coverage_when_fuel: float | None
    bad_queue_probability_when_known: float | None
    avg_queue_severity_when_fuel: float | None
    very_bad_queue_probability_when_known: float | None
    service_unavailable_ratio: float | None

    model_config = ConfigDict(from_attributes=True)


class GetStationStatsCmd(BaseModel):
    station_id: str
