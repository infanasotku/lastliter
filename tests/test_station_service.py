import pytest
from mock import AsyncMock, MagicMock
from pytest import fixture

from app.domains.station import Station
from app.dto.station import SyncStationCmd, SyncStationResult
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
    return client


@fixture()
def svc(uow: MagicMock, gdebenz: MagicMock) -> StationService:
    return StationService(
        uow,
        gdebenz=gdebenz,
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
