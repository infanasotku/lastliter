from types import SimpleNamespace
from typing import Any, cast

import pytest
from mock import AsyncMock, MagicMock

from app.controllers.admin.views.station import StationView
from app.controllers.admin.views.station_map import StationMapView, _get_origin
from app.dto.station import StationDTO


def test_station_views_share_stations_category():
    assert StationView.name_plural == "All"
    assert StationView.icon == "fa-solid fa-list"
    assert StationView.category == "Stations"
    assert StationView.category_icon == "fa-solid fa-gas-pump"

    assert StationMapView.name == "Map"
    assert StationMapView.icon == "fa-regular fa-map"
    assert StationMapView.category == "Stations"
    assert StationMapView.category_icon == "fa-solid fa-gas-pump"


@pytest.mark.asyncio
async def test_station_map_view_delegates_station_loading_to_service():
    view = StationMapView()
    svc = SimpleNamespace(get_all_stations=AsyncMock(return_value=[]))

    result = await view.get_all_stations(svc=svc)

    assert result == []
    svc.get_all_stations.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_station_map_view_renders_iframe_page():
    view = StationMapView()
    view.map_url = "https://map.example.test/app"
    stations = [
        StationDTO(
            id="station-1",
            name="Test station",
            address="Test address",
            lat=54.99,
            lon=82.98,
            score=0.7,
            confidence=0.5,
        )
    ]
    get_all_stations_mock = AsyncMock(return_value=stations)
    cast(Any, view).get_all_stations = get_all_stations_mock
    template_response = MagicMock()
    template_response_mock = AsyncMock(return_value=template_response)
    cast(Any, view).templates = SimpleNamespace(TemplateResponse=template_response_mock)
    request = MagicMock()
    request.url_for.return_value = "https://admin.example.test/station/details/station-1"

    response = await view.station_map(request)

    assert response is template_response
    get_all_stations_mock.assert_awaited_once_with()
    template_response_mock.assert_awaited_once_with(
        request,
        "station_map.html",
        {
            "map_url": "https://map.example.test/app",
            "map_bridge_config": {
                "mapOrigin": "https://map.example.test",
                "context": {
                    "type": "lastliter:admin-context",
                    "version": 2,
                    "mode": "admin",
                    "capabilities": {"openStation": True},
                    "stations": [
                        {
                            "id": "station-1",
                            "name": "Test station",
                            "address": "Test address",
                            "latitude": 54.99,
                            "longitude": 82.98,
                            "score": 0.7,
                            "confidence": 0.5,
                        }
                    ],
                },
                "stationDetailsUrls": {"station-1": "https://admin.example.test/station/details/station-1"},
            },
        },
    )


def test_map_origin_uses_only_scheme_and_authority():
    assert _get_origin("http://localhost:5173/map?q=1") == "http://localhost:5173"


@pytest.mark.parametrize("url", ["localhost:5173", "ftp://map.example.test"])
def test_map_origin_rejects_non_http_absolute_url(url: str):
    with pytest.raises(ValueError):
        _get_origin(url)
