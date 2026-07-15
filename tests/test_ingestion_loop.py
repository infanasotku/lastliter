import asyncio

import pytest
from mock import AsyncMock, MagicMock

from app.controllers.loop import ingestion
from app.dto.ingestion import RunIngestionIterationCmd


class TestRunIngestionLoop:
    @pytest.mark.asyncio
    async def test_sleeps_when_iteration_has_no_work(self, monkeypatch: pytest.MonkeyPatch):
        svc = MagicMock()
        svc.run_ingestion_iteration = AsyncMock(return_value=False)
        sleep = AsyncMock(side_effect=asyncio.CancelledError)
        monkeypatch.setattr(ingestion.asyncio, "sleep", sleep)
        loop = ingestion.IngestionLoop()

        with pytest.raises(asyncio.CancelledError):
            await loop._run_loop(
                RunIngestionIterationCmd(owner=loop._loop_id, pipeline_type="fetch_raw"),
                svc=svc,
            )

        svc.run_ingestion_iteration.assert_awaited_once()
        cmd = svc.run_ingestion_iteration.await_args.args[0]
        assert isinstance(cmd, RunIngestionIterationCmd)
        assert cmd.owner
        assert cmd.pipeline_type == "fetch_raw"
        sleep.assert_awaited_once_with(ingestion.IDLE_SLEEP_SECONDS)

    @pytest.mark.asyncio
    async def test_immediately_starts_next_iteration_when_work_was_processed(self, monkeypatch: pytest.MonkeyPatch):
        svc = MagicMock()
        svc.run_ingestion_iteration = AsyncMock(side_effect=[True, False])
        sleep = AsyncMock(side_effect=asyncio.CancelledError)
        monkeypatch.setattr(ingestion.asyncio, "sleep", sleep)
        loop = ingestion.IngestionLoop()

        with pytest.raises(asyncio.CancelledError):
            await loop._run_loop(
                RunIngestionIterationCmd(owner=loop._loop_id, pipeline_type="fetch_raw"),
                svc=svc,
            )

        assert svc.run_ingestion_iteration.await_count == 2
        first_cmd, second_cmd = [call.args[0] for call in svc.run_ingestion_iteration.await_args_list]
        assert first_cmd.owner == second_cmd.owner
        assert first_cmd.pipeline_type == second_cmd.pipeline_type == "fetch_raw"
        sleep.assert_awaited_once_with(ingestion.IDLE_SLEEP_SECONDS)
