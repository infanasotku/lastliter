from dataclasses import dataclass
from datetime import datetime, timedelta


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
            fetch_interval_sec=300,
            priority=0,
        )

    last_fetched_at: datetime
    next_fetch_at: datetime
    fetch_interval_sec: int
    priority: int = 0

    def update_fetch_info(self, *, now: datetime, observations_fetched: int) -> None:
        self.last_fetched_at = now
        self.next_fetch_at = now + timedelta(seconds=self.fetch_interval_sec)

        # TODO: implement a more sophisticated algorithm for adjusting fetch_interval_sec and priority based on observations
