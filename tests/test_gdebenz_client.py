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


@pytest.mark.asyncio
async def test_get_station_by_shared_link_parses_json_style_share_station_script():
    share_html = """
        <meta name="gb-build" content="15e1d51|1783960536|0|app.f13e56f6520c.js">
        <script>window.SHARE_STATION={"osm_id": "12995781578", "lat": 54.8752569, "lon": 83.076535, "name": "Газпромнефть", "addr": "Бердское шоссе, 470", "snapshot": {"status": "no", "fuels_now": "", "confirmations": 33, "created_at": "2026-07-13 17:13:48"}};</script>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/s/ia8yPzs0c0_d7VCbO4rNdQ":
            return httpx.Response(200, text=share_html)

        assert request.url.path == "/api/nearby"
        assert dict(request.url.params) == {
            "lat": "54.8752569",
            "lon": "83.076535",
            "radius_km": "20",
        }
        return httpx.Response(
            200,
            json={
                "summary": {},
                "stations": [
                    {
                        "osm_id": "12995781578",
                        "name": "Газпромнефть",
                        "addr": "Бердское шоссе, 470",
                        "lat": 54.8752569,
                        "lon": 83.076535,
                    },
                ],
            },
        )

    client = HTTPGdeBenzClient(GdebenzSettings(fingerprint="test"))
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client._client:
        station = await client.get_station_by_shared_link("https://gdebenz.ru/s/ia8yPzs0c0_d7VCbO4rNdQ")

    assert station.id == "12995781578"
    assert station.name == "Газпромнефть"
    assert station.address == "Бердское шоссе, 470"
    assert station.lat == 54.8752569
    assert station.lon == 83.076535
