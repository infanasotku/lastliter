import pytest
from mock import AsyncMock, MagicMock

from app.controllers.tasks import station
from app.dto.station import AddStationsByAreaCmd, AddStationsByAreaFilters


class TestAddStationsByAreaTask:
    def test_normalizes_request_payload_and_runs_async_handler(self, monkeypatch: pytest.MonkeyPatch):
        runtime = MagicMock()
        captured = {}

        def add_stations_by_area(req: station.AddStationsByAreaRequest) -> str:
            captured["req"] = req
            return "coroutine"

        monkeypatch.setattr(station, "get_runtime", MagicMock(return_value=runtime))
        monkeypatch.setattr(station, "add_stations_by_area", add_stations_by_area)

        station.add_stations_by_area_task.run(
            {
                "lat1": 55,
                "lon1": 82,
                "lat2": 56,
                "lon2": 83,
                "filters": {
                    "by_id": "station-1",
                    "by_name": "Gazprom",
                },
            }
        )

        assert captured["req"] == station.AddStationsByAreaRequest(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
            filters=AddStationsByAreaFilters(by_id="station-1", by_name="Gazprom"),
        )
        runtime.run.assert_called_once_with("coroutine")

    def test_worker_app_registers_station_task(self):
        from app.entrypoints.worker import create_app

        app = create_app()

        app.loader.import_default_modules()

        assert "app.controllers.tasks.station.add_stations_by_area_task" in app.tasks


class TestAddStationsByArea:
    @pytest.mark.asyncio
    async def test_calls_station_service_with_add_by_area_command(self):
        svc = MagicMock()
        svc.add_by_area.process = AsyncMock()
        req = station.AddStationsByAreaRequest(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
            filters=AddStationsByAreaFilters(by_id="station-1", by_name="Gazprom"),
        )

        await station.add_stations_by_area(req, svc=svc)

        svc.add_by_area.process.assert_awaited_once_with(
            AddStationsByAreaCmd(
                lat1=55,
                lon1=82,
                lat2=56,
                lon2=83,
                filters=AddStationsByAreaFilters(by_id="station-1", by_name="Gazprom"),
            )
        )
