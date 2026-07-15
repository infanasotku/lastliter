import pytest
from mock import AsyncMock, MagicMock
from pytest import fixture

from app.domains.exception import StationNotFoundError
from app.domains.state import PipelineType
from app.domains.station import Station
from app.dto.station import (
    AddStationBySharedLinkCmd,
    AddStationsByAreaCmd,
    AddStationsByAreaFilters,
    AddStationsByAreaResult,
    GetStationStatsCmd,
    StartAddStationBySharedLinkCmd,
    StartAddStationsByAreaCmd,
    StationHourlyStats,
)
from app.services.station import StationService


@fixture()
def station_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.stations = MagicMock()
    ctx.stations.insert_many_safe = AsyncMock()
    ctx.states = MagicMock()
    ctx.states.insert_many_safe = AsyncMock(return_value=0)
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
def svc(uow: MagicMock, click_ctx: MagicMock, gdebenz: MagicMock) -> StationService:
    return StationService(
        uow,
        click_ctx=click_ctx,
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


class TestStationServiceAddStationsByArea:
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
        station_ctx.stations.insert_many_safe.return_value = [valid_station, another_valid_station]
        station_ctx.states.insert_many_safe.return_value = 2
        gdebenz.get_stations.return_value = [
            valid_station,
            empty_name_station,
            empty_address_station,
            another_valid_station,
        ]
        cmd = AddStationsByAreaCmd(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
        )

        result = await svc.add_by_area.process(cmd)

        assert result == AddStationsByAreaResult(inserted_count=2)
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
        state_args = station_ctx.states.insert_many_safe.await_args.args[0]
        assert [state.station_id for state in state_args] == ["station-1", "station-4"]
        assert [state.pipeline_type for state in state_args] == [PipelineType.FETCH_RAW, PipelineType.FETCH_RAW]
        assert all(state.interval_sec == 300 for state in state_args)
        assert all(state.priority == 0 for state in state_args)
        assert all(state.error is None for state in state_args)

    @pytest.mark.asyncio
    async def test_filters_stations_by_name(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        matching_station = make_station("station-1", name="Gazprom")
        station_ctx.stations.insert_many_safe.return_value = [matching_station]
        other_station = make_station("station-2", name="Lukoil")
        gdebenz.get_stations.return_value = [
            matching_station,
            other_station,
        ]
        cmd = AddStationsByAreaCmd(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
            filters=AddStationsByAreaFilters(by_name="gaz"),
        )

        result = await svc.add_by_area.process(cmd)

        assert result == AddStationsByAreaResult(inserted_count=1)
        station_ctx.stations.insert_many_safe.assert_awaited_once_with([matching_station])
        state_args = station_ctx.states.insert_many_safe.await_args.args[0]
        assert [state.station_id for state in state_args] == ["station-1"]

    @pytest.mark.asyncio
    async def test_filters_stations_by_id(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        matching_station = make_station("station-1", name="Gazprom")
        station_ctx.stations.insert_many_safe.return_value = [matching_station]
        other_station = make_station("station-2", name="Gazprom")
        gdebenz.get_stations.return_value = [
            matching_station,
            other_station,
        ]
        cmd = AddStationsByAreaCmd(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
            filters=AddStationsByAreaFilters(by_id="station-1"),
        )

        result = await svc.add_by_area.process(cmd)

        assert result == AddStationsByAreaResult(inserted_count=1)
        station_ctx.stations.insert_many_safe.assert_awaited_once_with([matching_station])
        state_args = station_ctx.states.insert_many_safe.await_args.args[0]
        assert [state.station_id for state in state_args] == ["station-1"]

    @pytest.mark.asyncio
    async def test_returns_zero_when_all_stations_are_filtered_out(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        station_ctx.stations.insert_many_safe.return_value = []
        gdebenz.get_stations.return_value = [
            make_station("station-1", name=""),
            make_station("station-2", address=""),
        ]
        cmd = AddStationsByAreaCmd(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
        )

        result = await svc.add_by_area.process(cmd)

        assert result == AddStationsByAreaResult(inserted_count=0)
        station_ctx.stations.insert_many_safe.assert_awaited_once_with([])
        station_ctx.states.insert_many_safe.assert_awaited_once_with([])


class TestStationServiceStartAddStationsByArea:
    @pytest.mark.asyncio
    async def test_schedules_add_by_area_task_with_plain_request_payload(
        self,
        svc: StationService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        apply_async = MagicMock()
        monkeypatch.setattr("app.controllers.tasks.station.add_stations_by_area_task.apply_async", apply_async)
        cmd = StartAddStationsByAreaCmd(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
            correlation_id="request-id",
            filters=AddStationsByAreaFilters(by_id="station-1", by_name="Gazprom"),
        )

        await svc.add_by_area.start(cmd)

        apply_async.assert_called_once_with(
            kwargs={
                "req": {
                    "lat1": 55.0,
                    "lon1": 82.0,
                    "lat2": 56.0,
                    "lon2": 83.0,
                    "filters": {
                        "by_id": "station-1",
                        "by_name": "Gazprom",
                    },
                }
            },
            task_id="request-id",
        )


class TestStationServiceAddStationBySharedLink:
    @pytest.mark.asyncio
    async def test_inserts_station_found_by_shared_link(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        station = make_station("station-1", name="Gazprom")
        gdebenz.get_station_by_shared_link = AsyncMock(return_value=station)
        station_ctx.stations.insert_many_safe.return_value = [station]
        station_ctx.states.insert_many_safe.return_value = 1
        cmd = AddStationBySharedLinkCmd(shared_link="https://gdebenz.ru/s/token")

        result = await svc.add_by_shared_link.process(cmd)

        assert result is True
        gdebenz.get_station_by_shared_link.assert_awaited_once_with("https://gdebenz.ru/s/token")
        station_ctx.stations.insert_many_safe.assert_awaited_once_with([station])
        state_args = station_ctx.states.insert_many_safe.await_args.args[0]
        assert [state.station_id for state in state_args] == ["station-1"]
        assert state_args[0].pipeline_type == PipelineType.FETCH_RAW

    @pytest.mark.asyncio
    async def test_returns_false_when_station_is_not_found_by_shared_link(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        gdebenz.get_station_by_shared_link = AsyncMock(return_value=None)
        cmd = AddStationBySharedLinkCmd(shared_link="https://gdebenz.ru/s/unknown")

        result = await svc.add_by_shared_link.process(cmd)

        assert result is False
        gdebenz.get_station_by_shared_link.assert_awaited_once_with("https://gdebenz.ru/s/unknown")
        station_ctx.stations.insert_many_safe.assert_not_awaited()
        station_ctx.states.insert_many_safe.assert_not_awaited()


class TestStationServiceStartAddStationBySharedLink:
    @pytest.mark.asyncio
    async def test_schedules_add_by_shared_link_task_with_plain_request_payload(
        self,
        svc: StationService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        apply_async = MagicMock()
        monkeypatch.setattr("app.controllers.tasks.station.add_station_by_shared_link_task.apply_async", apply_async)
        cmd = StartAddStationBySharedLinkCmd(
            shared_link="https://gdebenz.ru/s/token",
            correlation_id="request-id",
        )

        await svc.add_by_shared_link.start(cmd)

        apply_async.assert_called_once_with(
            kwargs={
                "req": {
                    "shared_link": "https://gdebenz.ru/s/token",
                }
            },
            task_id="request-id",
        )


class TestStationServiceGetLinkByStationId:
    @pytest.mark.asyncio
    async def test_returns_shared_link_for_existing_station(
        self,
        svc: StationService,
        uow: MagicMock,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        station_ctx.stations.get_by_id = AsyncMock(return_value=make_station("station-1"))
        gdebenz.get_shared_link_by_station_id = AsyncMock(return_value="https://gdebenz.ru/s/token")

        result = await svc.get_link_by_station_id("station-1")

        assert result == "https://gdebenz.ru/s/token"
        uow.begin.assert_called_once_with(write=False)
        station_ctx.stations.get_by_id.assert_awaited_once_with("station-1")
        gdebenz.get_shared_link_by_station_id.assert_awaited_once_with("station-1")

    @pytest.mark.asyncio
    async def test_raises_when_station_is_not_found(
        self,
        svc: StationService,
        uow: MagicMock,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        station_ctx.stations.get_by_id = AsyncMock(return_value=None)
        gdebenz.get_shared_link_by_station_id = AsyncMock()

        with pytest.raises(StationNotFoundError, match="Station with id station-1 not found"):
            await svc.get_link_by_station_id("station-1")

        uow.begin.assert_called_once_with(write=False)
        station_ctx.stations.get_by_id.assert_awaited_once_with("station-1")
        gdebenz.get_shared_link_by_station_id.assert_not_awaited()


class TestStationServiceGetStationStats:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_clickhouse_has_no_stats(
        self,
        svc: StationService,
        click_ctx: MagicMock,
    ):
        click_ctx.stations.get_station_hourly_stats = AsyncMock(return_value=[])

        result = await svc.get_station_stats(GetStationStatsCmd(station_id="station-1"))

        assert result == []
        click_ctx.stations.get_station_hourly_stats.assert_awaited_once_with(station_id="station-1")

    @pytest.mark.asyncio
    async def test_calculates_scores_from_hourly_stats(
        self,
        svc: StationService,
        click_ctx: MagicMock,
    ):
        click_ctx.stations.get_station_hourly_stats = AsyncMock(
            return_value=[
                StationHourlyStats(
                    weekday=1,
                    hour=8,
                    observations_count=10,
                    fuel_available_ratio=0.8,
                    queue_probability_when_known=0.5,
                    queue_data_coverage_when_fuel=0.75,
                    bad_queue_probability_when_known=0.25,
                    avg_queue_severity_when_fuel=2.0,
                    very_bad_queue_probability_when_known=0.1,
                    service_unavailable_ratio=0.2,
                ),
                StationHourlyStats(
                    weekday=2,
                    hour=9,
                    observations_count=3,
                    fuel_available_ratio=None,
                    queue_probability_when_known=None,
                    queue_data_coverage_when_fuel=None,
                    bad_queue_probability_when_known=None,
                    avg_queue_severity_when_fuel=None,
                    very_bad_queue_probability_when_known=None,
                    service_unavailable_ratio=None,
                ),
            ]
        )

        result = await svc.get_station_stats(GetStationStatsCmd(station_id="station-1"))

        assert [score.hour for score in result] == [8, 9]
        assert [score.weekday for score in result] == [1, 2]
        assert result[0].score == pytest.approx(0.5475)
        assert result[0].confidence == pytest.approx(0.575)
        assert result[1].score is None
        assert result[1].confidence == pytest.approx(0.105)
