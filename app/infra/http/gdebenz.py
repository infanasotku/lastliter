import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime

import httpx

from app.domains.station import Station
from app.dto.station import RawStationObservation
from app.infra.common.time import now_utc
from app.infra.config.gdebenz import GdebenzSettings

BASE_URL = "https://www.gdebenz.ru/api"
SITE_URL = "https://www.gdebenz.ru"
STATIONS_PATH = "/stations"
NEARBY_PATH = "/nearby"
EVENTS_PATH = "/comments/{id}/recent?limit={limit}&fp={fingerprint}"
SHARE_PATH = "/s/{token}"
NEARBY_RADIUS_KM = 20
SHARE_STATION_RE = re.compile(r"window\.SHARE_STATION\s*=\s*{")
OSM_ID_RE = re.compile(r"""osm_id:\s*['"](?P<value>[^'"]+)['"]""")
LAT_RE = re.compile(r"lat:\s*(?P<value>-?\d+(?:\.\d+)?)")
LON_RE = re.compile(r"lon:\s*(?P<value>-?\d+(?:\.\d+)?)")


class HTTPGdeBenzClient:
    def __init__(self, settings: GdebenzSettings) -> None:
        self._client = httpx.AsyncClient(
            http2=True,
            headers={
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
            },
        )
        self._settings = settings

    @staticmethod
    def _to_station(row: dict) -> Station:
        return Station.new(
            id=row["osm_id"],
            name=row["name"],
            address=row["addr"],
            lat=row["lat"],
            lon=row["lon"],
            now=now_utc(),
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

        return [self._to_station(row) for row in rows]

    async def get_obs_by_id(self, id: str, limit: int = 10) -> list[RawStationObservation]:
        url = f"{BASE_URL}{EVENTS_PATH.format(id=id, limit=limit, fingerprint=self._settings.fingerprint)}"

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

    async def get_station_by_shared_link(self, shared_link: str) -> Station:
        token = shared_link.rstrip("/").rsplit("/", maxsplit=1)[-1]
        if not token:
            raise ValueError(f"Could not extract token from shared link: {shared_link}")

        url = f"{SITE_URL}{SHARE_PATH.format(token=token)}"
        share_station_started = False
        share_data: dict[str, str] = {}
        patterns = {
            "osm_id": OSM_ID_RE,
            "lat": LAT_RE,
            "lon": LON_RE,
        }

        async with self._client.stream("GET", url) as r:
            r.raise_for_status()

            async for line in r.aiter_lines():
                if not share_station_started:
                    share_station_started = bool(SHARE_STATION_RE.search(line))
                    if not share_station_started:
                        continue

                for field, pattern in patterns.items():
                    if field not in share_data and (match := pattern.search(line)):
                        share_data[field] = match.group("value")

                if len(share_data) == len(patterns):
                    break

        if len(share_data) != len(patterns):
            raise ValueError(f"Could not find station coordinates and osm_id by shared link: {shared_link}")

        nearby_url = f"{BASE_URL}{NEARBY_PATH}"
        r = await self._client.get(
            nearby_url,
            params={
                "lat": float(share_data["lat"]),
                "lon": float(share_data["lon"]),
                "radius_km": NEARBY_RADIUS_KM,
            },
        )
        r.raise_for_status()

        osm_id = share_data["osm_id"]
        row = next((row for row in r.json()["stations"] if row["osm_id"] == osm_id), None)
        if row is None:
            raise ValueError(f"Could not find station {osm_id} within {NEARBY_RADIUS_KM} km")

        return self._to_station(row)


@asynccontextmanager
async def create_gdebenz_client(settings: GdebenzSettings) -> AsyncGenerator[HTTPGdeBenzClient]:
    client = HTTPGdeBenzClient(settings=settings)
    async with client._client:
        yield client
