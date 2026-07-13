import httpx
import pytest

from app.infra.config.gdebenz import GdebenzSettings
from app.infra.http.gdebenz import HTTPGdeBenzClient


@pytest.mark.asyncio
async def test_get_station_by_shared_link_uses_nearby_and_filters_by_osm_id():
    share_html = """
        <script>
          window.SHARE_STATION = {
            osm_id: '13285799037',
            lat: 55.0158558,
            lon: 82.9223572,
          };
        </script>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/s/Oca0lKAOVVcWDcZ5mlCUlA":
            return httpx.Response(200, text=share_html)

        assert request.url.path == "/api/nearby"
        assert dict(request.url.params) == {
            "lat": "55.0158558",
            "lon": "82.9223572",
            "radius_km": "20",
        }
        return httpx.Response(
            200,
            json={
                "summary": {},
                "stations": [
                    {
                        "osm_id": "another-station",
                        "name": "Другая АЗС",
                        "addr": "Другой адрес",
                        "lat": 55.0,
                        "lon": 82.9,
                    },
                    {
                        "osm_id": "13285799037",
                        "name": "Энергия",
                        "addr": "ул Фабричная, 4А",
                        "lat": 55.0158558,
                        "lon": 82.9223572,
                    },
                ],
            },
        )

    client = HTTPGdeBenzClient(GdebenzSettings(fingerprint="test"))
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client._client:
        station = await client.get_station_by_shared_link("https://gdebenz.ru/s/Oca0lKAOVVcWDcZ5mlCUlA")

    assert station.id == "13285799037"
    assert station.name == "Энергия"
    assert station.address == "ул Фабричная, 4А"
    assert station.lat == 55.0158558
    assert station.lon == 82.9223572
