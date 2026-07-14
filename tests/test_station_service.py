import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from mock import ANY, AsyncMock, MagicMock, call
from pytest import fixture

from app.domains.exception import StationNotFoundError
from app.domains.station import Station
from app.dto.station import (
    AddStationBySharedLinkCmd,
    AddStationsByAreaCmd,
    AddStationsByAreaFilters,
    AddStationsByAreaResult,
    GetStationStatsCmd,
    RawStationObservation,
    RunIngestionIterationCmd,
    StartAddStationBySharedLinkCmd,
    StartAddStationsByAreaCmd,
    StationHourlyStats,
)
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

    @pytest.mark.asyncio
    async def test_filters_stations_by_name(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        station_ctx.stations.insert_many_safe.return_value = 1
        matching_station = make_station("station-1", name="Gazprom")
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

    @pytest.mark.asyncio
    async def test_filters_stations_by_id(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        station_ctx.stations.insert_many_safe.return_value = 1
        matching_station = make_station("station-1", name="Gazprom")
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
        cmd = AddStationsByAreaCmd(
            lat1=55,
            lon1=82,
            lat2=56,
            lon2=83,
        )

        result = await svc.add_by_area.process(cmd)

        assert result == AddStationsByAreaResult(inserted_count=0)
        station_ctx.stations.insert_many_safe.assert_awaited_once_with([])


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
        station_ctx.stations.insert_many_safe.return_value = 1
        cmd = AddStationBySharedLinkCmd(shared_link="https://gdebenz.ru/s/token")

        result = await svc.add_by_shared_link.process(cmd)

        assert result is True
        gdebenz.get_station_by_shared_link.assert_awaited_once_with("https://gdebenz.ru/s/token")
        station_ctx.stations.insert_many_safe.assert_awaited_once_with([station])

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
                ),
            ]
        )

        result = await svc.get_station_stats(GetStationStatsCmd(station_id="station-1"))

        assert [score.hour for score in result] == [8, 9]
        assert [score.weekday for score in result] == [1, 2]
        assert result[0].score == pytest.approx(0.57875)
        assert result[0].confidence == pytest.approx(0.575)
        assert result[1].score is None
        assert result[1].confidence == pytest.approx(0.105)


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
        station_ctx.stations.claim_stations = AsyncMock(return_value=[])
        station_ctx.stations.update_claimed_stations = AsyncMock()

        has_work = await svc.run_ingestion_iteration(RunIngestionIterationCmd(owner="worker-1"))

        assert has_work is False
        station_ctx.stations.claim_stations.assert_awaited_once_with(
            now=ANY,
            limit=10,
            owner="worker-1",
            claim_for=timedelta(minutes=5),
        )
        limiter.wait.assert_not_awaited()
        gdebenz.get_obs_by_id.assert_not_awaited()
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.stations.update_claimed_stations.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_true_when_due_stations_are_processed(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        station = make_station("station-1")
        station_ctx.stations.claim_stations = AsyncMock(return_value=[station])
        station_ctx.stations.update_claimed_stations = AsyncMock(return_value=1)
        gdebenz.get_obs_by_id = AsyncMock(return_value=[])

        has_work = await svc.run_ingestion_iteration(RunIngestionIterationCmd(owner="worker-1"))

        assert has_work is True
        station_ctx.stations.claim_stations.assert_awaited_once_with(
            now=ANY,
            limit=10,
            owner="worker-1",
            claim_for=timedelta(minutes=5),
        )
        click_ctx.stations.insert_raw_observations.assert_awaited_once_with([])
        station_ctx.stations.update_claimed_stations.assert_awaited_once_with([station], owner="worker-1", now=ANY)

    @pytest.mark.asyncio
    async def test_marks_failed_fetch_and_continues_with_other_stations(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        failed_station = make_station("station-1")
        successful_station = make_station("station-2", name="Other")
        station_ctx.stations.claim_stations = AsyncMock(return_value=[failed_station, successful_station])
        station_ctx.stations.update_claimed_stations = AsyncMock(return_value=1)

        async def get_obs_by_id(station_id: str, *, limit: int):
            if station_id == failed_station.id:
                raise RuntimeError("upstream unavailable")
            return []

        gdebenz.get_obs_by_id = AsyncMock(side_effect=get_obs_by_id)

        has_work = await svc.run_ingestion_iteration(RunIngestionIterationCmd(owner="worker-1"))

        assert has_work is True
        assert failed_station.fetch_error == "upstream unavailable"
        assert successful_station.fetch_error is None
        click_ctx.stations.insert_raw_observations.assert_awaited_once_with([])
        station_ctx.stations.update_claimed_stations.assert_has_awaits(
            [
                call([failed_station], owner="worker-1", now=ANY),
                call([successful_station], owner="worker-1", now=ANY),
            ]
        )

    @pytest.mark.asyncio
    async def test_retries_individual_observations_when_bulk_clickhouse_insert_fails(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        first_station = make_station("station-1")
        second_station = make_station("station-2", name="Other")
        station_ctx.stations.claim_stations = AsyncMock(return_value=[first_station, second_station])
        station_ctx.stations.update_claimed_stations = AsyncMock(return_value=2)
        observation = RawStationObservation(
            status="yes",
            detail="available",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            author_reliable=True,
            on_site=True,
        )
        gdebenz.get_obs_by_id = AsyncMock(return_value=[observation])

        async def insert_raw_observations(observations):
            if len(observations) > 1 or observations[0].station_id == second_station.id:
                raise RuntimeError("clickhouse unavailable")

        click_ctx.stations.insert_raw_observations = AsyncMock(side_effect=insert_raw_observations)

        has_work = await svc.run_ingestion_iteration(RunIngestionIterationCmd(owner="worker-1"))

        assert has_work is True
        assert first_station.fetch_error is None
        assert second_station.fetch_error == "clickhouse unavailable"
        assert click_ctx.stations.insert_raw_observations.await_count == 3
        station_ctx.stations.update_claimed_stations.assert_awaited_once_with(
            [first_station, second_station], owner="worker-1", now=ANY
        )

    @pytest.mark.asyncio
    async def test_marks_all_stations_failed_and_skips_clickhouse_when_every_fetch_fails(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        stations = [make_station("station-1"), make_station("station-2", name="Other")]
        station_ctx.stations.claim_stations = AsyncMock(return_value=stations)
        station_ctx.stations.update_claimed_stations = AsyncMock(return_value=2)
        gdebenz.get_obs_by_id = AsyncMock(side_effect=RuntimeError("upstream unavailable"))

        has_work = await svc.run_ingestion_iteration(RunIngestionIterationCmd(owner="worker-1"))

        assert has_work is False
        assert [station.fetch_error for station in stations] == ["upstream unavailable", "upstream unavailable"]
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.stations.update_claimed_stations.assert_awaited_once_with(stations, owner="worker-1", now=ANY)

    @pytest.mark.asyncio
    async def test_inserts_normalized_observation_and_rate_limits_each_station(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
        limiter: MagicMock,
    ):
        station = make_station("station-1")
        raw = RawStationObservation(
            status="queue",
            detail="long queue",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            author_reliable=True,
            on_site=False,
        )
        station_ctx.stations.claim_stations = AsyncMock(return_value=[station])
        station_ctx.stations.update_claimed_stations = AsyncMock(return_value=1)
        gdebenz.get_obs_by_id = AsyncMock(return_value=[raw])

        has_work = await svc.run_ingestion_iteration(RunIngestionIterationCmd(owner="worker-1"))

        assert has_work is True
        limiter.wait.assert_awaited_once_with(key="lastliter:stations:fetch:limit", limit_per_second=2)
        gdebenz.get_obs_by_id.assert_awaited_once_with("station-1", limit=20)
        inserted = click_ctx.stations.insert_raw_observations.await_args.args[0]
        assert len(inserted) == 1
        assert inserted[0].station_id == station.id
        assert inserted[0].status == raw.status
        assert inserted[0].detail == raw.detail
        assert inserted[0].created_at == raw.created_at
        assert inserted[0].author_reliable is True
        assert inserted[0].on_site is False

    @pytest.mark.asyncio
    async def test_skips_clickhouse_when_heartbeat_loses_all_leases(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
        limiter: MagicMock,
    ):
        station = make_station("station-1")
        station_ctx.stations.claim_stations = AsyncMock(return_value=[station])
        station_ctx.stations.refresh_lease = AsyncMock(return_value=0)
        station_ctx.stations.update_claimed_stations = AsyncMock()
        gdebenz.get_obs_by_id = AsyncMock(return_value=[])

        async def yield_to_heartbeat(**_kwargs):
            await asyncio.sleep(0)

        limiter.wait = AsyncMock(side_effect=yield_to_heartbeat)

        has_work = await svc.run_ingestion_iteration(RunIngestionIterationCmd(owner="worker-1"))

        assert has_work is False
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.stations.update_claimed_stations.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inserts_only_stations_with_refreshed_lease_after_partial_lease_loss(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
        limiter: MagicMock,
    ):
        retained_station = make_station("station-1")
        lost_station = make_station("station-2", name="Other")
        raw = RawStationObservation(
            status="yes",
            detail="available",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            author_reliable=True,
            on_site=True,
        )
        station_ctx.stations.claim_stations = AsyncMock(return_value=[retained_station, lost_station])
        station_ctx.stations.refresh_lease = AsyncMock(return_value=1)
        station_ctx.stations.get_claimed = AsyncMock(return_value=[retained_station])
        station_ctx.stations.update_claimed_stations = AsyncMock(return_value=1)
        gdebenz.get_obs_by_id = AsyncMock(return_value=[raw])

        async def yield_to_heartbeat(**_kwargs):
            await asyncio.sleep(0)

        limiter.wait = AsyncMock(side_effect=yield_to_heartbeat)

        has_work = await svc.run_ingestion_iteration(RunIngestionIterationCmd(owner="worker-1"))

        assert has_work is True
        inserted = click_ctx.stations.insert_raw_observations.await_args.args[0]
        assert [observation.station_id for observation in inserted] == [retained_station.id]
        station_ctx.stations.update_claimed_stations.assert_awaited_once_with(
            [retained_station, lost_station], owner="worker-1", now=ANY
        )

    @pytest.mark.asyncio
    async def test_skips_clickhouse_when_heartbeat_raises(
        self,
        svc: StationService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
        limiter: MagicMock,
    ):
        station = make_station("station-1")
        station_ctx.stations.claim_stations = AsyncMock(return_value=[station])
        station_ctx.stations.refresh_lease = AsyncMock(side_effect=RuntimeError("postgres unavailable"))
        station_ctx.stations.update_claimed_stations = AsyncMock()
        gdebenz.get_obs_by_id = AsyncMock(return_value=[])

        async def yield_to_heartbeat(**_kwargs):
            await asyncio.sleep(0)

        limiter.wait = AsyncMock(side_effect=yield_to_heartbeat)

        has_work = await svc.run_ingestion_iteration(RunIngestionIterationCmd(owner="worker-1"))

        assert has_work is False
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.stations.update_claimed_stations.assert_not_awaited()
