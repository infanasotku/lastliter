import asyncio

import pytest
from mock import AsyncMock, MagicMock

from app.controllers.loop import station


class TestRunIngestionLoop:
    @pytest.mark.asyncio
    async def test_sleeps_when_iteration_has_no_work(self, monkeypatch: pytest.MonkeyPatch):
        svc = MagicMock()
        svc.run_ingestion_iteration = AsyncMock(return_value=False)
        sleep = AsyncMock(side_effect=asyncio.CancelledError)
        monkeypatch.setattr(station.asyncio, "sleep", sleep)

        with pytest.raises(asyncio.CancelledError):
            await station.run_ingestion_loop(svc=svc)

        svc.run_ingestion_iteration.assert_awaited_once()
        sleep.assert_awaited_once_with(station.IDLE_SLEEP_SECONDS)
