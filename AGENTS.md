# AGENTS.md - lastliter

## Project Focus

lastliter predicts when to visit a specific fuel station to avoid queues or fuel
unavailability.

This is a historical and predictive analytics service based on crowd-sourced
observations, not a real-time map app. Real-time snapshots are useful context,
but the main product value comes from event history, state transitions, and
uncertainty-aware recommendations.

## Read First

- Source API examples and payload shapes live in `sources/`:
  - `sources/stations.md` - station registry / dimension data.
  - `sources/nearby.md` - geospatial current snapshot for map/current-state UX.
  - `sources/comments.md` - station-level current aggregate and confidence data.
  - `sources/recent_comments.md` - per-station event stream; primary analytics input.
- Ingestion architecture lives in `docs/ingestion_loop.md`.

Check these docs before changing ingestion, normalization, analytics contracts, or
source-specific parsing.

## Core Model

- `stations` is the dimension table.
- `station_events` is the append-only fact stream derived directly from
  `/api/comments/{station_id}/recent`.
- Analytics should work from normalized raw events, not from an invented
  intermediate event layer.
- Current-state endpoints such as `/api/nearby` and `/api/comments/{station_id}`
  should not be treated as historical truth.

## State And Metrics

Station status should be interpreted as state over time:

- `yes` -> available
- `low` -> low fuel
- `queue` -> queue
- `no` -> no fuel

Primary analytics questions:

- What state transitions happened before and after congestion?
- How long do queue or outage states usually last?
- What patterns repeat by station, weekday, and hour?
- How reliable and fresh are the observations?

Core metrics are `queue_probability`, `fuel_unavailability_probability`,
`average_event_duration`, `confidence_score`, and `sample_count`.

## Ingestion Rules

Follow `docs/ingestion_loop.md`:

- Postgres decides what and when to fetch.
- Workers execute fetches and stay stateless about scheduling.
- ClickHouse stores immutable event history.
- Scheduling feedback updates Postgres after ingestion.
- Multi-worker ingestion must remain safe via locked station selection.

## Product Rules

- Always expose uncertainty and data sparsity.
- Lower confidence when samples are sparse, stale, contradictory, or unreliable.
- Prefer best/worst time windows over fake precise predictions.
- MVP output should include 2-3 best windows, worst windows, and confidence.

## Agent Mental Model

Think in terms of station behavior over time:

- state transitions
- weekly/hourly repetition
- observation reliability
- confidence under noisy crowd-sourced data

Do not optimize only for latest snapshots, map rendering, or storing upstream
responses without analytics value.
