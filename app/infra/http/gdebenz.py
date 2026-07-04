import httpx

from app.domains.station import Station

BASE_URL = "https://gdebenz.ru/api"
STATIONS_PATH = "/stations"


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

        async with self._client as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            rows = r.json()

        def _to_station(row: dict) -> Station:
            return Station(
                id=row["osm_id"],
                name=row["name"],
                address=row["addr"],
                lat=row["lat"],
                lon=row["lon"],
            )

        return [_to_station(row) for row in rows]
