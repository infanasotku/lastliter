from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime

import httpx

from app.domains.station import Station
from app.dto.station import RawStationObservation
from app.infra.common.time import now_utc

BASE_URL = "https://www.gdebenz.ru/api"
STATIONS_PATH = "/stations"
EVENTS_PATH = "/comments/{id}/recent?limit={limit}"


class HTTPGdeBenzClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            http2=True,
            headers={
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
            },
        )

    async def get_stations(
        self,
        *,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> list[Station]:
        url = f"{BASE_URL}{STATIONS_PATH}"
        params = {
            "lat1": lat1,
            "lon1": lon1,
            "lat2": lat2,
            "lon2": lon2,
        }

        r = await self._client.get(url, params=params)
        r.raise_for_status()
        rows = r.json()

        def _to_station(row: dict) -> Station:
            return Station.new(
                id=row["osm_id"],
                name=row["name"],
                address=row["addr"],
                lat=row["lat"],
                lon=row["lon"],
                now=now_utc(),
            )

        return [_to_station(row) for row in rows]

    async def get_obs_by_id(self, id: str, limit: int = 10) -> list[RawStationObservation]:
        url = f"{BASE_URL}{EVENTS_PATH.format(id=id, limit=limit)}"

        r = await self._client.get(url)
        r.raise_for_status()
        rows = r.json()

        def _to_event(row: dict) -> RawStationObservation:
            return RawStationObservation(
                status=row["status"],
                detail=row["detail"],
                created_at=datetime.fromisoformat(row["created_at"]),
                author_reliable=row["author_reliable"],
                on_site=row.get("on_site", False),
            )

        return [_to_event(row) for row in rows]


@asynccontextmanager
async def create_gdebenz_client() -> AsyncGenerator[HTTPGdeBenzClient]:
    client = HTTPGdeBenzClient()
    async with client._client:
        yield client
