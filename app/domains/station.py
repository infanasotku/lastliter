from dataclasses import dataclass


@dataclass
class Station:
    id: str

    name: str
    address: str

    lat: float
    lon: float
