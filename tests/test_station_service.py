from datetime import datetime, timezone

import pytest
from mock import AsyncMock, MagicMock
from pytest import fixture

from app.domains.station import Station
from app.dto.station import StartSyncStationCmd, SyncStationCmd, SyncStationResult
from app.services.station import StationService


@fixture()
def station_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.stations = MagicMock()
    ctx.stations.insert_many_safe = AsyncMock(return_value=2)
    return ctx


@fixture()
def uow(station_ctx: MagicMock) -> MagicMock:
    uow = MagicMock()

    manager = AsyncMock()
    manager.__aenter__.return_value = station_ctx
    manager.__aexit__.return_value = None

    uow.begin.return_value = manager
    return uow


@fixture()
def gdebenz() -> MagicMock:
    client = MagicMock()
    client.get_stations = AsyncMock()
    client.get_obs_by_id = AsyncMock()
    return client


@fixture()
def click_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.stations = MagicMock()
    ctx.stations.insert_raw_observations = AsyncMock()
    return ctx


@fixture()
def limiter() -> MagicMock:
    limiter = MagicMock()
    limiter.wait = AsyncMock()
    return limiter


@fixture()
def svc(uow: MagicMock, click_ctx: MagicMock, gdebenz: MagicMock, limiter: MagicMock) -> StationService:
    return StationService(
        uow,
        click_ctx=click_ctx,
        gdebenz=gdebenz,
        limiter=limiter,
    )


def make_station(
    station_id: str,
    *,
    name: str = "Station",
    address: str = "Fuel street",
) -> Station:
    return Station(
        id=station_id,
        name=name,
        address=address,
        lat=55.1,
        lon=82.2,
        last_fetched_at=datetime.min.replace(tzinfo=timezone.utc),
        next_fetch_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetch_interval_sec=300,
    )


class TestStationServiceSyncStations:
    @pytest.mark.asyncio
    async def test_fetches_stations_filters_invalid_rows_and_inserts_valid_ones(
        self,
        svc: StationService,
        uow: MagicMock,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        valid_station = make_station("station-1")
        empty_name_station = make_station("station-2", name="")
        empty_address_station = make_station("station-3", address="")
        another_valid_station = make_station("station-4", name="Another", address="Another street")
        gdebenz.get_stations.return_value = [
            valid_station,
            empty_name_station,
            empty_address_station,
            another_valid_station,
        ]
        cmd = SyncStationCmd(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
        )

        result = await svc.sync_stations(cmd)

        assert result == SyncStationResult(new=2)
        gdebenz.get_stations.assert_awaited_once_with(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
        )
        uow.begin.assert_called_once_with(write=True)
        station_ctx.stations.insert_many_safe.assert_awaited_once_with(
            [
                valid_station,
                another_valid_station,
            ]
        )

    @pytest.mark.asyncio
    async def test_returns_zero_when_all_stations_are_filtered_out(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        station_ctx.stations.insert_many_safe.return_value = 0
        gdebenz.get_stations.return_value = [
            make_station("station-1", name=""),
            make_station("station-2", address=""),
        ]
        cmd = SyncStationCmd(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
        )

        result = await svc.sync_stations(cmd)

        assert result == SyncStationResult(new=0)
        station_ctx.stations.insert_many_safe.assert_awaited_once_with([])


class TestStationServiceStartSyncStations:
    @pytest.mark.asyncio
    async def test_schedules_sync_task_with_plain_request_payload(
        self,
        svc: StationService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        apply_async = MagicMock()
        monkeypatch.setattr("app.controllers.tasks.station.sync_stations_task.apply_async", apply_async)
        cmd = StartSyncStationCmd(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
            correlation_id="request-id",
        )

        await svc.start_sync_stations(cmd)

        apply_async.assert_called_once_with(
            kwargs={
                "req": {
                    "lat1": 55.0,
                    "lon1": 82.0,
                    "lat2": 56.0,
                    "lon2": 83.0,
                }
            },
            task_id="request-id",
        )


class TestStationServiceRunIngestionIteration:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_stations_are_due(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
        limiter: MagicMock,
    ):
        station_ctx.stations.get_stations_for_fetch_for_update = AsyncMock(return_value=[])
        station_ctx.stations.update_stations = AsyncMock()

        has_work = await svc.run_ingestion_iteration()

        assert has_work is False
        limiter.wait.assert_not_awaited()
        gdebenz.get_obs_by_id.assert_not_awaited()
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.stations.update_stations.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_true_when_due_stations_are_processed(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        station = make_station("station-1")
        station_ctx.stations.get_stations_for_fetch_for_update = AsyncMock(return_value=[station])
        station_ctx.stations.update_stations = AsyncMock()
        gdebenz.get_obs_by_id = AsyncMock(return_value=[])

        has_work = await svc.run_ingestion_iteration()

        assert has_work is True
        click_ctx.stations.insert_raw_observations.assert_awaited_once_with([])
        station_ctx.stations.update_stations.assert_awaited_once_with([station])
