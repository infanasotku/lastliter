from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from markupsafe import Markup
from mock import AsyncMock, MagicMock
from starlette.datastructures import URL as StarletteURL
from starlette.datastructures import FormData

from app.controllers.admin.views.station import AddStationBySharedLinkForm, AddStationsByAreaForm, StationView
from app.domains.station import StationScore
from app.dto.station import (
    AddStationsByAreaFilters,
    GetStationStatsCmd,
    StartAddStationBySharedLinkCmd,
    StartAddStationsByAreaCmd,
)
from app.infra.common.correlation import RequestContext, with_request_context
from app.infra.postgres.models.station import Station


def make_request(
    *,
    method: str = "GET",
    form: FormData | None = None,
    query_params: dict[str, str] | None = None,
    path_params: dict[str, str] | None = None,
) -> MagicMock:
    request = MagicMock()
    request.method = method
    request.form = AsyncMock(return_value=form or FormData())
    request.query_params = query_params or {}
    request.path_params = path_params or {}
    request.url_for = MagicMock(
        side_effect=lambda name, **_: StarletteURL(
            {
                "admin:view-station-add_station_by_shared_link_form": "http://testserver/station/add-by-shared-link",
                "admin:view-station-add_stations_by_area_form": "http://testserver/station/add-by-area",
                "admin:view-station-station_stats": "http://testserver/station/stats/station-1",
                "admin:list": "http://testserver/station/list",
            }[name]
        )
    )
    return request


def mock_templates(view: StationView, template_response: MagicMock) -> AsyncMock:
    template_response_mock = AsyncMock(return_value=template_response)
    cast(Any, view).templates = SimpleNamespace(TemplateResponse=template_response_mock)
    return template_response_mock


def awaited_args(mock: AsyncMock) -> tuple[Any, ...]:
    assert mock.await_args is not None
    return mock.await_args.args


class TestStationViewAddStationsByAreaFormAction:
    @pytest.mark.asyncio
    async def test_redirects_to_add_by_area_form(self):
        view = StationView()
        request = make_request()

        response = await view.add_stations_by_area_form_action(request)

        request.url_for.assert_called_once_with("admin:view-station-add_stations_by_area_form")
        assert response.status_code == 303
        assert response.headers["location"] == "http://testserver/station/add-by-area"


class TestStationViewAddStationBySharedLinkFormAction:
    @pytest.mark.asyncio
    async def test_redirects_to_add_by_shared_link_form(self):
        view = StationView()
        request = make_request()

        response = await view.add_station_by_shared_link_form_action(request)

        request.url_for.assert_called_once_with("admin:view-station-add_station_by_shared_link_form")
        assert response.status_code == 303
        assert response.headers["location"] == "http://testserver/station/add-by-shared-link"


class TestStationViewStationStats:
    @pytest.mark.asyncio
    async def test_redirects_action_to_station_stats_page(self):
        view = StationView()
        request = make_request(query_params={"pks": "station-1"})

        response = await view.station_stats_action(request)

        request.url_for.assert_called_once_with("admin:view-station-station_stats", station_id="station-1")
        assert response.status_code == 303
        assert response.headers["location"] == "http://testserver/station/stats/station-1"

    @pytest.mark.asyncio
    async def test_renders_station_stats_page(self):
        view = StationView()
        view.get_stats = AsyncMock(
            return_value=[
                StationScore(hour=8, weekday=1, score=0.7, confidence=0.5),
                StationScore(hour=9, weekday=2, score=None, confidence=0.1),
            ]
        )
        template_response = MagicMock()
        template_response_mock = mock_templates(view, template_response)
        request = make_request(path_params={"station_id": "station-1"})

        response = await view.station_stats(request)

        assert response is template_response
        view.get_stats.assert_awaited_once_with(GetStationStatsCmd(station_id="station-1"))
        _, template_name, context = awaited_args(template_response_mock)
        assert template_name == "station_stats.html"
        assert context["station_id"] == "station-1"
        assert context["scores"] == [
            {"confidence": 0.5, "hour": 8, "score": 0.7, "weekday": 1},
            {"confidence": 0.1, "hour": 9, "score": None, "weekday": 2},
        ]
        assert context["list_url"] == "http://testserver/station/list"


class TestStationViewGdebenz:
    def test_gdebenz_returns_extend_link_markup(self):
        view = StationView()
        station = Station(
            id="station 1",
            name="Station",
            address="Address",
            description=None,
            lat=55.1,
            lon=82.2,
            last_fetched_at=datetime(2026, 7, 14, tzinfo=UTC),
            next_fetch_at=datetime(2026, 7, 14, tzinfo=UTC),
            fetch_interval_sec=3600,
            fetch_error=None,
            priority=1,
            claimed_by=None,
            lease_until=None,
        )

        link = view.gdebenz(station, "gdebenz")

        assert isinstance(link, Markup)
        assert str(link) == (
            '<a href="/admin/station/extend/station%201" target="_blank" rel="noopener noreferrer">gdebenz</a>'
        )

    @pytest.mark.asyncio
    async def test_extend_redirects_to_generated_gdebenz_link(self):
        view = StationView()
        get_link_by_station_id = AsyncMock(return_value="https://gdebenz.ru/s/token")
        cast(Any, view).get_link_by_station_id = get_link_by_station_id
        request = make_request(path_params={"station_id": "station-1"})

        response = await view.extend(request)

        get_link_by_station_id.assert_awaited_once_with("station-1")
        assert response.status_code == 303
        assert response.headers["location"] == "https://gdebenz.ru/s/token"


class TestStationViewAddStationsByAreaForm:
    @pytest.mark.asyncio
    async def test_renders_form_on_get(self):
        view = StationView()
        template_response = MagicMock()
        template_response_mock = mock_templates(view, template_response)
        request = make_request()

        response = await view.add_stations_by_area_form(request)

        assert response is template_response
        template_response_mock.assert_awaited_once()
        _, template_name, context = awaited_args(template_response_mock)
        assert template_name == "station_add_by_area.html"
        assert isinstance(context["form"], AddStationsByAreaForm)
        assert context["form_action_url"] == "http://testserver/station/add-by-area"
        assert context["list_url"] == "http://testserver/station/list"
        assert context["model_view"] is view

    @pytest.mark.asyncio
    async def test_builds_cmd_starts_add_by_area_and_redirects_to_list_on_valid_post(self):
        view = StationView()
        view.start_add_stations_by_area = AsyncMock()
        request = make_request(
            method="POST",
            form=FormData(
                {
                    "lat1": "55.1",
                    "lon1": "82.2",
                    "lat2": "56.3",
                    "lon2": "83.4",
                    "by_id": "  station-1  ",
                    "by_name": "  Gazprom  ",
                }
            ),
        )

        with with_request_context(RequestContext(request_id="request-id")):
            response = await view.add_stations_by_area_form(request)

        view.start_add_stations_by_area.assert_awaited_once_with(
            StartAddStationsByAreaCmd(
                lat1=55.1,
                lon1=82.2,
                lat2=56.3,
                lon2=83.4,
                correlation_id="request-id",
                filters=AddStationsByAreaFilters(by_id="station-1", by_name="Gazprom"),
            )
        )
        request.url_for.assert_called_with("admin:list", identity="station")
        assert response.status_code == 303
        assert response.headers["location"] == "http://testserver/station/list"

    @pytest.mark.asyncio
    async def test_renders_form_and_does_not_start_add_by_area_on_invalid_post(self):
        view = StationView()
        view.start_add_stations_by_area = AsyncMock()
        template_response = MagicMock()
        template_response_mock = mock_templates(view, template_response)
        request = make_request(
            method="POST",
            form=FormData(
                {
                    "lat1": "91",
                    "lon1": "82.2",
                    "lat2": "56.3",
                    "lon2": "83.4",
                }
            ),
        )

        response = await view.add_stations_by_area_form(request)

        assert response is template_response
        view.start_add_stations_by_area.assert_not_awaited()
        _, _, context = awaited_args(template_response_mock)
        assert "lat1" in context["form"].errors


class TestStationViewBuildAddStationsByAreaCmd:
    def test_builds_cmd_from_valid_form(self):
        form = AddStationsByAreaForm(
            FormData(
                {
                    "lat1": "55.1",
                    "lon1": "82.2",
                    "lat2": "56.3",
                    "lon2": "83.4",
                    "by_id": "  station-1  ",
                    "by_name": "  Gazprom  ",
                }
            )
        )
        assert form.validate()

        with with_request_context(RequestContext(request_id="request-id")):
            cmd = StationView()._build_add_stations_by_area_cmd(form)

        assert cmd == StartAddStationsByAreaCmd(
            lat1=55.1,
            lon1=82.2,
            lat2=56.3,
            lon2=83.4,
            correlation_id="request-id",
            filters=AddStationsByAreaFilters(by_id="station-1", by_name="Gazprom"),
        )

    def test_raises_when_form_data_is_missing(self):
        form = AddStationsByAreaForm()

        with pytest.raises(ValueError, match="missing required coordinates"):
            StationView()._build_add_stations_by_area_cmd(form)


class TestStationViewAddStationBySharedLinkForm:
    @pytest.mark.asyncio
    async def test_renders_form_on_get(self):
        view = StationView()
        template_response = MagicMock()
        template_response_mock = mock_templates(view, template_response)
        request = make_request()

        response = await view.add_station_by_shared_link_form(request)

        assert response is template_response
        template_response_mock.assert_awaited_once()
        _, template_name, context = awaited_args(template_response_mock)
        assert template_name == "station_add_by_shared_link.html"
        assert isinstance(context["form"], AddStationBySharedLinkForm)
        assert context["form_action_url"] == "http://testserver/station/add-by-shared-link"
        assert context["list_url"] == "http://testserver/station/list"
        assert context["model_view"] is view

    @pytest.mark.asyncio
    async def test_builds_cmd_starts_add_by_shared_link_and_redirects_to_list_on_valid_post(self):
        view = StationView()
        view.start_add_station_by_shared_link = AsyncMock()
        request = make_request(
            method="POST",
            form=FormData(
                {
                    "shared_link": "  https://gdebenz.ru/s/Oca0lKAOVVcWDcZ5mlCUlA  ",
                }
            ),
        )

        with with_request_context(RequestContext(request_id="request-id")):
            response = await view.add_station_by_shared_link_form(request)

        view.start_add_station_by_shared_link.assert_awaited_once_with(
            StartAddStationBySharedLinkCmd(
                shared_link="https://gdebenz.ru/s/Oca0lKAOVVcWDcZ5mlCUlA",
                correlation_id="request-id",
            )
        )
        request.url_for.assert_called_with("admin:list", identity="station")
        assert response.status_code == 303
        assert response.headers["location"] == "http://testserver/station/list"

    @pytest.mark.asyncio
    async def test_renders_form_and_does_not_start_add_by_shared_link_on_invalid_post(self):
        view = StationView()
        view.start_add_station_by_shared_link = AsyncMock()
        template_response = MagicMock()
        template_response_mock = mock_templates(view, template_response)
        request = make_request(method="POST", form=FormData({"shared_link": ""}))

        response = await view.add_station_by_shared_link_form(request)

        assert response is template_response
        view.start_add_station_by_shared_link.assert_not_awaited()
        _, _, context = awaited_args(template_response_mock)
        assert "shared_link" in context["form"].errors


class TestStationViewBuildAddStationBySharedLinkCmd:
    def test_builds_cmd_from_valid_form(self):
        form = AddStationBySharedLinkForm(
            FormData(
                {
                    "shared_link": "  https://gdebenz.ru/s/Oca0lKAOVVcWDcZ5mlCUlA  ",
                }
            )
        )
        assert form.validate()

        with with_request_context(RequestContext(request_id="request-id")):
            cmd = StationView()._build_add_station_by_shared_link_cmd(form)

        assert cmd == StartAddStationBySharedLinkCmd(
            shared_link="https://gdebenz.ru/s/Oca0lKAOVVcWDcZ5mlCUlA",
            correlation_id="request-id",
        )

    def test_raises_when_shared_link_is_missing(self):
        form = AddStationBySharedLinkForm()

        with pytest.raises(ValueError, match="missing shared link"):
            StationView()._build_add_station_by_shared_link_cmd(form)
