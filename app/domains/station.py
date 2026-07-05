from dataclasses import dataclass
from datetime import datetime


@dataclass
class Station:
    id: str

    name: str
    address: str

    lat: float
    lon: float

    @classmethod
    def new(cls, *, id: str, name: str, address: str, lat: float, lon: float, now: datetime) -> "Station":
        return cls(
            id=id,
            name=name,
            address=address,
            lat=lat,
            lon=lon,
            last_fetched_at=datetime.min,
            next_fetch_at=now,
            fetch_interval_sec=0,
            priority=0,
        )

    last_fetched_at: datetime
    next_fetch_at: datetime
    fetch_interval_sec: int
    priority: int = 0
