# Ingestion Loop Architecture (LastLiter)

## Core principle

Postgres decides WHAT to fetch
Worker executes fetch
ClickHouse stores history
Postgres adjusts WHEN to fetch next

## System flow

## [1] Postgres (Scheduler / State Store)

Responsible for deciding WHAT to fetch next.

Stores:

- station_id
- last_fetched_at
- next_fetch_at
- fetch_interval_sec
- priority_score (optional)

Selection logic:

- SELECT stations WHERE next_fetch_at <= now()
- ORDER BY priority DESC, last_fetched_at ASC
- FOR UPDATE SKIP LOCKED (multi-worker safe)

## [2] Worker (Ingestion Loop / Execution Engine)

Responsible for executing ingestion.

Flow:

- fetch batch of due stations from Postgres
- call external API:
  GET /api/comments/{station_id}/recent
- normalize response → events
- write events to ClickHouse
- handle retries + rate limiting
- continue loop (continuous execution)

Important:

- Worker is stateless regarding scheduling
- Worker does NOT decide WHAT to fetch

## [3] ClickHouse (Event Store)

Responsible for storing immutable history.

Stores:

- station_id
- timestamp
- status (queue / yes / no / low)
- metadata (confidence, author_reliable, raw payload)

Properties:

- append-only
- optimized for analytics queries
- no updates, no scheduling logic

## [4] Postgres (Scheduling Feedback Loop)

After successful ingestion:

UPDATE stations SET:

- last_fetched_at = now()
- next_fetch_at = now() + dynamic_interval
- fetch_interval_sec = adjusted_value

Adjustment rules:

- high volatility → decrease interval (faster polling)
- stable state → increase interval
- stale/missing data → increase priority

## Concurrency model

- multiple workers supported
- safe parallel execution via:
  FOR UPDATE SKIP LOCKED
- no duplicate station processing across workers

## Key properties

- no cursor / offset ingestion
- no batch continuation state
- fully restartable system
- horizontally scalable
- rate-limit aware
- adaptive scheduling
- continuous ingestion loop

## Deferred operational work

- Configure explicit HTTP connect/read timeouts and a bounded retry policy for
  GdeBenz requests. Retries must fit within the station lease or renew it.
- Add and validate a Postgres index for due-station claiming. The index should
  support `next_fetch_at`, lease expiration, priority, and `last_fetched_at`
  used by the scheduler query.

## Mental model

Postgres → scheduler brain (WHAT + WHEN)
Worker → execution engine (HOW)
ClickHouse → historical truth (WHAT happened)
