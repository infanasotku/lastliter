from types import SimpleNamespace
from typing import Any, cast

import pytest
from mock import AsyncMock, MagicMock
from starlette.datastructures import URL as StarletteURL
from starlette.datastructures import FormData

from app.controllers.admin.views.station import StationSyncForm, StationView
from app.domains.station import StationScore
from app.dto.station import GetStationStatsCmd, StartSyncStationCmd
from app.infra.common.correlation import RequestContext, with_request_context


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
                "admin:view-station-sync_stations_form": "http://testserver/station/sync",
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


class TestStationViewSyncStationsFormAction:
    @pytest.mark.asyncio
    async def test_redirects_to_sync_form(self):
        view = StationView()
        request = make_request()

        response = await view.sync_stations_form_action(request)

        request.url_for.assert_called_once_with("admin:view-station-sync_stations_form")
        assert response.status_code == 303
        assert response.headers["location"] == "http://testserver/station/sync"


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


class TestStationViewSyncStationsForm:
    @pytest.mark.asyncio
    async def test_renders_form_on_get(self):
        view = StationView()
        template_response = MagicMock()
        template_response_mock = mock_templates(view, template_response)
        request = make_request()

        response = await view.sync_stations_form(request)

        assert response is template_response
        template_response_mock.assert_awaited_once()
        _, template_name, context = awaited_args(template_response_mock)
        assert template_name == "station_sync.html"
        assert isinstance(context["form"], StationSyncForm)
        assert context["form_action_url"] == "http://testserver/station/sync"
        assert context["list_url"] == "http://testserver/station/list"
        assert context["model_view"] is view

    @pytest.mark.asyncio
    async def test_builds_cmd_calls_sync_and_redirects_to_list_on_valid_post(self):
        view = StationView()
        view.sync_stations = AsyncMock()
        request = make_request(
            method="POST",
            form=FormData(
                {
                    "lat1": "55.1",
                    "lon1": "82.2",
                    "lat2": "56.3",
                    "lon2": "83.4",
                }
            ),
        )

        with with_request_context(RequestContext(request_id="request-id")):
            response = await view.sync_stations_form(request)

        view.sync_stations.assert_awaited_once_with(
            StartSyncStationCmd(
                lat1=55.1,
                lon1=82.2,
                lat2=56.3,
                lon2=83.4,
                correlation_id="request-id",
            )
        )
        request.url_for.assert_called_with("admin:list", identity="station")
        assert response.status_code == 303
        assert response.headers["location"] == "http://testserver/station/list"

    @pytest.mark.asyncio
    async def test_renders_form_and_does_not_sync_on_invalid_post(self):
        view = StationView()
        view.sync_stations = AsyncMock()
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

        response = await view.sync_stations_form(request)

        assert response is template_response
        view.sync_stations.assert_not_awaited()
        _, _, context = awaited_args(template_response_mock)
        assert "lat1" in context["form"].errors


class TestStationViewBuildSyncStationsCmd:
    def test_builds_cmd_from_valid_form(self):
        form = StationSyncForm(
            FormData(
                {
                    "lat1": "55.1",
                    "lon1": "82.2",
                    "lat2": "56.3",
                    "lon2": "83.4",
                }
            )
        )
        assert form.validate()

        with with_request_context(RequestContext(request_id="request-id")):
            cmd = StationView()._build_sync_stations_cmd(form)

        assert cmd == StartSyncStationCmd(
            lat1=55.1,
            lon1=82.2,
            lat2=56.3,
            lon2=83.4,
            correlation_id="request-id",
        )

    def test_raises_when_form_data_is_missing(self):
        form = StationSyncForm()

        with pytest.raises(ValueError, match="missing required coordinates"):
            StationView()._build_sync_stations_cmd(form)
