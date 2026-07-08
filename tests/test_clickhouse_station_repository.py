from datetime import datetime, timezone

import pytest
from mock import AsyncMock, MagicMock

from app.dto.station import InsertObservation
from app.infra.clickhouse.repositories.station import ClickStationRepository


def make_observation(observation_id: int) -> InsertObservation:
    return InsertObservation(
        id=observation_id,
        station_id="station-1",
        status="yes",
        detail="ok",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        author_reliable=True,
        on_site=False,
    )


class TestClickStationRepository:
    @pytest.mark.asyncio
    async def test_filters_existing_and_in_batch_duplicate_observations(self):
        client = MagicMock()
        client.query = AsyncMock()
        client.insert = AsyncMock()
        client.query.return_value.result_rows = [(1,)]
        repo = ClickStationRepository(client)

        await repo.insert_raw_observations(
            [
                make_observation(1),
                make_observation(2),
                make_observation(2),
                make_observation(3),
            ]
        )

        client.insert.assert_awaited_once()
        _, kwargs = client.insert.await_args
        assert kwargs["data"] == [
            (2, "station-1", datetime(2026, 1, 1, tzinfo=timezone.utc), "yes", "ok", True, False),
            (3, "station-1", datetime(2026, 1, 1, tzinfo=timezone.utc), "yes", "ok", True, False),
        ]

    @pytest.mark.asyncio
    async def test_skips_insert_when_all_observations_already_exist(self):
        client = MagicMock()
        client.query = AsyncMock()
        client.insert = AsyncMock()
        client.query.return_value.result_rows = [(1,), (2,)]
        repo = ClickStationRepository(client)

        await repo.insert_raw_observations([make_observation(1), make_observation(2)])

        client.insert.assert_not_awaited()
