import pytest
from mock import AsyncMock, MagicMock

from app.controllers.tasks import station
from app.dto.station import SyncStationCmd


class TestSyncStationsTask:
    def test_normalizes_request_payload_and_runs_async_handler(self, monkeypatch: pytest.MonkeyPatch):
        runtime = MagicMock()
        captured = {}

        def sync_stations(req: station.SyncStationRequest) -> str:
            captured["req"] = req
            return "coroutine"

        monkeypatch.setattr(station, "get_runtime", MagicMock(return_value=runtime))
        monkeypatch.setattr(station, "sync_stations", sync_stations)

        station.sync_stations_task.run(
            {
                "lat1": 55,
                "lon1": 82,
                "lat2": 56,
                "lon2": 83,
            }
        )

        assert captured["req"] == station.SyncStationRequest(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
        )
        runtime.run.assert_called_once_with("coroutine")

    def test_worker_app_registers_station_task(self):
        from app.entrypoints.worker import create_app

        app = create_app()

        app.loader.import_default_modules()

        assert "app.controllers.tasks.station.sync_stations_task" in app.tasks


class TestSyncStations:
    @pytest.mark.asyncio
    async def test_calls_station_service_with_sync_command(self):
        svc = MagicMock()
        svc.sync_stations = AsyncMock()
        req = station.SyncStationRequest(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
        )

        await station.sync_stations(req, svc=svc)

        svc.sync_stations.assert_awaited_once_with(
            SyncStationCmd(
                lat1=55,
                lon1=82,
                lat2=56,
                lon2=83,
            )
        )
