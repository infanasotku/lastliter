from datetime import datetime, timezone

import pytest
from mock import AsyncMock, MagicMock

from app.dto.ingestion import InsertObservation
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

    @pytest.mark.asyncio
    async def test_get_station_hourly_stats_maps_clickhouse_rows(self):
        client = MagicMock()
        client.query = AsyncMock()
        client.query.return_value.result_rows = [
            (1, 8, 12, 0.75, 1.5, 0.8, 0.25, 0.1, 0.05, 0.2),
            (7, 20, 4, None, None, None, None, None, None, None),
        ]
        repo = ClickStationRepository(client)

        stats = await repo.get_station_hourly_stats("station-1")

        assert [stat.model_dump() for stat in stats] == [
            {
                "weekday": 1,
                "hour": 8,
                "observations_count": 12,
                "fuel_available_ratio": 0.75,
                "avg_queue_severity_when_fuel": 1.5,
                "queue_data_coverage_when_fuel": 0.8,
                "queue_probability_when_known": 0.25,
                "bad_queue_probability_when_known": 0.1,
                "very_bad_queue_probability_when_known": 0.05,
                "service_unavailable_ratio": 0.2,
            },
            {
                "weekday": 7,
                "hour": 20,
                "observations_count": 4,
                "fuel_available_ratio": None,
                "avg_queue_severity_when_fuel": None,
                "queue_data_coverage_when_fuel": None,
                "queue_probability_when_known": None,
                "bad_queue_probability_when_known": None,
                "very_bad_queue_probability_when_known": None,
                "service_unavailable_ratio": None,
            },
        ]
        query = client.query.await_args.args[0]
        assert "FROM station_hourly_stats_v" in query
        assert "WHERE station_id = 'station-1'" in query
        assert "ORDER BY hour" in query

    @pytest.mark.asyncio
    async def test_get_stations_stats_for_spot_preserves_station_order_and_gaps(self):
        client = MagicMock()
        client.query = AsyncMock()
        client.query.return_value.result_rows = [
            (1, 8, 12, 0.75, 1.5, 0.8, 0.25, 0.1, 0.05, 0.2, "station-2"),
        ]
        repo = ClickStationRepository(client)

        stats = await repo.get_stations_stats_for_spot(
            ["station-1", "station-2", "station-3"],
            hour=8,
            weekday=1,
        )

        assert stats[0] is None
        assert stats[1] is not None
        assert stats[1].observations_count == 12
        assert stats[2] is None
        query = client.query.await_args.args[0]
        assert "station_id IN {station_ids:Array(String)}" in query
        assert client.query.await_args.kwargs["parameters"] == {
            "station_ids": ["station-1", "station-2", "station-3"],
            "hour": 8,
            "weekday": 1,
        }
