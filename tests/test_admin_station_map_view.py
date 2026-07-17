from types import SimpleNamespace
from typing import Any, cast

import pytest
from mock import AsyncMock, MagicMock

from app.controllers.admin.views.station import StationView
from app.controllers.admin.views.station_map import StationMapView


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
async def test_station_map_view_renders_iframe_page():
    view = StationMapView()
    view.map_url = "https://map.example.test"
    template_response = MagicMock()
    template_response_mock = AsyncMock(return_value=template_response)
    cast(Any, view).templates = SimpleNamespace(TemplateResponse=template_response_mock)
    request = MagicMock()

    response = await view.station_map(request)

    assert response is template_response
    template_response_mock.assert_awaited_once_with(
        request,
        "station_map.html",
        {"map_url": "https://map.example.test"},
    )
