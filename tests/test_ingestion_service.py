import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from mock import ANY, AsyncMock, MagicMock
from pytest import fixture

from app.domains.state import IngestionPipelineState, PipelineType
from app.dto.ingestion import RawStationObservation, RunIngestionIterationCmd
from app.services.ingestion import IngestionService


@fixture()
def station_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.states = MagicMock()
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


def make_state(
    station_id: str,
    *,
    pipeline_type: PipelineType = PipelineType.FETCH_RAW,
) -> IngestionPipelineState:
    return IngestionPipelineState(
        station_id=station_id,
        pipeline_type=pipeline_type,
        last_processed_at=datetime.min.replace(tzinfo=timezone.utc),
        next_run_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        interval_sec=300,
        priority=0,
        meta={},
    )


def make_ingestion_cmd(owner: str = "worker-1") -> RunIngestionIterationCmd:
    return RunIngestionIterationCmd(owner=owner, pipeline_type="fetch_raw")


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
        station_ctx.states.claim_states = AsyncMock(return_value=[])
        station_ctx.states.update_claimed_states = AsyncMock()

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is False
        station_ctx.states.claim_states.assert_awaited_once_with(
            now=ANY,
            limit=10,
            owner="worker-1",
            claim_for=timedelta(minutes=5),
            pipeline_type=PipelineType.FETCH_RAW,
        )
        limiter.wait.assert_not_awaited()
        gdebenz.get_obs_by_id.assert_not_awaited()
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.states.update_claimed_states.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_true_when_due_stations_are_processed(
        self,
        svc: IngestionService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        state = make_state("station-1")
        station_ctx.states.claim_states = AsyncMock(return_value=[state])
        station_ctx.states.update_claimed_states = AsyncMock(return_value=1)
        gdebenz.get_obs_by_id = AsyncMock(return_value=[])

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is True
        station_ctx.states.claim_states.assert_awaited_once_with(
            now=ANY,
            limit=10,
            owner="worker-1",
            claim_for=timedelta(minutes=5),
            pipeline_type=PipelineType.FETCH_RAW,
        )
        click_ctx.stations.insert_raw_observations.assert_awaited_once_with([])
        station_ctx.states.update_claimed_states.assert_awaited_once_with(
            [state], owner="worker-1", now=ANY, pipeline_type=PipelineType.FETCH_RAW
        )

    @pytest.mark.asyncio
    async def test_marks_failed_fetch_and_continues_with_other_stations(
        self,
        svc: IngestionService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        failed_state = make_state("station-1")
        successful_state = make_state("station-2")
        station_ctx.states.claim_states = AsyncMock(return_value=[failed_state, successful_state])
        station_ctx.states.update_claimed_states = AsyncMock(return_value=1)

        async def get_obs_by_id(station_id: str, *, limit: int):
            if station_id == failed_state.station_id:
                raise RuntimeError("upstream unavailable")
            return []

        gdebenz.get_obs_by_id = AsyncMock(side_effect=get_obs_by_id)

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is True
        assert failed_state.error == "upstream unavailable"
        assert successful_state.error is None
        click_ctx.stations.insert_raw_observations.assert_awaited_once_with([])
        station_ctx.states.update_claimed_states.assert_awaited_once_with(
            [failed_state, successful_state], owner="worker-1", now=ANY, pipeline_type=PipelineType.FETCH_RAW
        )

    @pytest.mark.asyncio
    async def test_retries_individual_observations_when_bulk_clickhouse_insert_fails(
        self,
        svc: IngestionService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        first_state = make_state("station-1")
        second_state = make_state("station-2")
        station_ctx.states.claim_states = AsyncMock(return_value=[first_state, second_state])
        station_ctx.states.update_claimed_states = AsyncMock(return_value=2)
        observation = RawStationObservation(
            status="yes",
            detail="available",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            author_reliable=True,
            on_site=True,
        )
        gdebenz.get_obs_by_id = AsyncMock(return_value=[observation])

        async def insert_raw_observations(observations):
            if len(observations) > 1 or observations[0].station_id == second_state.station_id:
                raise RuntimeError("clickhouse unavailable")

        click_ctx.stations.insert_raw_observations = AsyncMock(side_effect=insert_raw_observations)

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is True
        assert first_state.error is None
        assert second_state.error == "clickhouse unavailable"
        assert click_ctx.stations.insert_raw_observations.await_count == 3
        station_ctx.states.update_claimed_states.assert_awaited_once_with(
            [first_state, second_state], owner="worker-1", now=ANY, pipeline_type=PipelineType.FETCH_RAW
        )

    @pytest.mark.asyncio
    async def test_marks_all_stations_failed_and_skips_clickhouse_when_every_fetch_fails(
        self,
        svc: IngestionService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
    ):
        states = [make_state("station-1"), make_state("station-2")]
        station_ctx.states.claim_states = AsyncMock(return_value=states)
        station_ctx.states.update_claimed_states = AsyncMock(return_value=2)
        gdebenz.get_obs_by_id = AsyncMock(side_effect=RuntimeError("upstream unavailable"))

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is False
        assert [state.error for state in states] == ["upstream unavailable", "upstream unavailable"]
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.states.update_claimed_states.assert_awaited_once_with(
            states, owner="worker-1", now=ANY, pipeline_type=PipelineType.FETCH_RAW
        )

    @pytest.mark.asyncio
    async def test_inserts_normalized_observation_and_rate_limits_each_station(
        self,
        svc: IngestionService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
        limiter: MagicMock,
    ):
        state = make_state("station-1")
        raw = RawStationObservation(
            status="queue",
            detail="long queue",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            author_reliable=True,
            on_site=False,
        )
        station_ctx.states.claim_states = AsyncMock(return_value=[state])
        station_ctx.states.update_claimed_states = AsyncMock(return_value=1)
        gdebenz.get_obs_by_id = AsyncMock(return_value=[raw])

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is True
        limiter.wait.assert_awaited_once_with(key="lastliter:stations:fetch:limit", limit_per_second=2)
        gdebenz.get_obs_by_id.assert_awaited_once_with("station-1", limit=20)
        inserted = click_ctx.stations.insert_raw_observations.await_args.args[0]
        assert len(inserted) == 1
        assert inserted[0].station_id == state.station_id
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
        state = make_state("station-1")
        station_ctx.states.claim_states = AsyncMock(return_value=[state])
        station_ctx.states.refresh_lease = AsyncMock(return_value=0)
        station_ctx.states.update_claimed_states = AsyncMock()
        gdebenz.get_obs_by_id = AsyncMock(return_value=[])

        async def yield_to_heartbeat(**_kwargs):
            await asyncio.sleep(0)

        limiter.wait = AsyncMock(side_effect=yield_to_heartbeat)

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is False
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.states.update_claimed_states.assert_awaited_once_with(
            [state], owner="worker-1", now=ANY, pipeline_type=PipelineType.FETCH_RAW
        )

    @pytest.mark.asyncio
    async def test_inserts_only_stations_with_refreshed_lease_after_partial_lease_loss(
        self,
        svc: IngestionService,
        station_ctx: MagicMock,
        click_ctx: MagicMock,
        gdebenz: MagicMock,
        limiter: MagicMock,
    ):
        retained_state = make_state("station-1")
        lost_state = make_state("station-2")
        raw = RawStationObservation(
            status="yes",
            detail="available",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            author_reliable=True,
            on_site=True,
        )
        station_ctx.states.claim_states = AsyncMock(return_value=[retained_state, lost_state])
        station_ctx.states.refresh_lease = AsyncMock(return_value=1)
        station_ctx.states.get_claimed = AsyncMock(return_value=[retained_state])
        station_ctx.states.update_claimed_states = AsyncMock(return_value=1)
        gdebenz.get_obs_by_id = AsyncMock(return_value=[raw])

        async def yield_to_heartbeat(**_kwargs):
            await asyncio.sleep(0)

        limiter.wait = AsyncMock(side_effect=yield_to_heartbeat)

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is True
        inserted = click_ctx.stations.insert_raw_observations.await_args.args[0]
        assert [observation.station_id for observation in inserted] == [retained_state.station_id]
        station_ctx.states.update_claimed_states.assert_awaited_once_with(
            [retained_state, lost_state], owner="worker-1", now=ANY, pipeline_type=PipelineType.FETCH_RAW
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
        state = make_state("station-1")
        station_ctx.states.claim_states = AsyncMock(return_value=[state])
        station_ctx.states.refresh_lease = AsyncMock(side_effect=RuntimeError("postgres unavailable"))
        station_ctx.states.update_claimed_states = AsyncMock()
        gdebenz.get_obs_by_id = AsyncMock(return_value=[])

        async def yield_to_heartbeat(**_kwargs):
            await asyncio.sleep(0)

        limiter.wait = AsyncMock(side_effect=yield_to_heartbeat)

        has_work = await svc.run_ingestion_iteration(make_ingestion_cmd())

        assert has_work is False
        click_ctx.stations.insert_raw_observations.assert_not_awaited()
        station_ctx.states.update_claimed_states.assert_awaited_once_with(
            [state], owner="worker-1", now=ANY, pipeline_type=PipelineType.FETCH_RAW
        )
