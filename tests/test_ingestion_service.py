import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from mock import ANY, AsyncMock, MagicMock
from pytest import fixture

from app.domains.station import Station
from app.dto.ingestion import RawStationObservation, RunIngestionIterationCmd
from app.services.ingestion import IngestionService


@fixture()
def station_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.stations = MagicMock()
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
def svc(uow: MagicMock, click_ctx: MagicMock, gdebenz: MagicMock, limiter: MagicMock) -> IngestionService:
    return IngestionService(
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


def make_ingestion_cmd(owner: str = "worker-1") -> RunIngestionIterationCmd:
    return RunIngestionIterationCmd(owner=owner, stage="fetch_raw")


class TestIngestionServiceRunIteration:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_stations_are_due(
        self,
        svc: IngestionService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
        limiter: MagicMock,
    ):
        station_ctx.stations.claim_stations = AsyncMock(return_value=[])
        station_ctx.stations.update_claimed_stations = AsyncMock()

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

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
        svc: IngestionService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        station = make_station("station-1")
        station_ctx.stations.claim_stations = AsyncMock(return_value=[station])
        station_ctx.stations.update_claimed_stations = AsyncMock(return_value=1)
        gdebenz.get_obs_by_id = AsyncMock(return_value=[])

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

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
        svc: IngestionService,
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

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is True
        assert failed_station.fetch_error == "upstream unavailable"
        assert successful_station.fetch_error is None
        click_ctx.stations.insert_raw_observations.assert_awaited_once_with([])
        station_ctx.stations.update_claimed_stations.assert_awaited_once_with(
            [failed_station, successful_station], owner="worker-1", now=ANY
        )

    @pytest.mark.asyncio
    async def test_retries_individual_observations_when_bulk_clickhouse_insert_fails(
        self,
        svc: IngestionService,
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

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

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
        svc: IngestionService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        stations = [make_station("station-1"), make_station("station-2", name="Other")]
        station_ctx.stations.claim_stations = AsyncMock(return_value=stations)
        station_ctx.stations.update_claimed_stations = AsyncMock(return_value=2)
        gdebenz.get_obs_by_id = AsyncMock(side_effect=RuntimeError("upstream unavailable"))

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is False
        assert [station.fetch_error for station in stations] == ["upstream unavailable", "upstream unavailable"]
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.stations.update_claimed_stations.assert_awaited_once_with(stations, owner="worker-1", now=ANY)

    @pytest.mark.asyncio
    async def test_inserts_normalized_observation_and_rate_limits_each_station(
        self,
        svc: IngestionService,
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

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

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
        svc: IngestionService,
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

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is False
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.stations.update_claimed_stations.assert_awaited_once_with([station], owner="worker-1", now=ANY)

    @pytest.mark.asyncio
    async def test_inserts_only_stations_with_refreshed_lease_after_partial_lease_loss(
        self,
        svc: IngestionService,
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

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is True
        inserted = click_ctx.stations.insert_raw_observations.await_args.args[0]
        assert [observation.station_id for observation in inserted] == [retained_station.id]
        station_ctx.stations.update_claimed_stations.assert_awaited_once_with(
            [retained_station, lost_station], owner="worker-1", now=ANY
        )

    @pytest.mark.asyncio
    async def test_skips_clickhouse_when_heartbeat_raises(
        self,
        svc: IngestionService,
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

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is False
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.stations.update_claimed_stations.assert_awaited_once_with([station], owner="worker-1", now=ANY)
