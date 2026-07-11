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
- priority
- lease_until
- claimed_by

Claim logic:

- pick due stations with no active lease:
  `next_fetch_at <= now()` and `lease_until IS NULL OR lease_until < now()`
- order by `priority DESC, last_fetched_at ASC`
- claim via short transaction:
  `FOR UPDATE SKIP LOCKED` + `lease_until = now() + claim_for` + `claimed_by = worker_id`
- worker keeps the claim alive with heartbeat while processing
- feedback update is guarded by `claimed_by` and active `lease_until`

## [2] Worker (Ingestion Loop / Execution Engine)

Responsible for executing ingestion.

Flow:

- claim batch of due stations from Postgres
- call external API:
  GET /api/comments/{station_id}/recent
- normalize response → events
- write events to ClickHouse
- update Postgres scheduling feedback for still-owned stations
- release claim by clearing `lease_until` / `claimed_by`
- handle per-station errors + rate limiting
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

After successful ingestion of still-owned stations:

UPDATE stations SET:

- last_fetched_at = now()
- next_fetch_at = now() + dynamic_interval
- fetch_interval_sec = adjusted_value
- lease_until = NULL
- claimed_by = NULL

Adjustment rules:

- high volatility → decrease interval (faster polling)
- stable state → increase interval
- stale/missing data → increase priority

## Concurrency model

- multiple workers supported
- safe parallel execution via:
  `FOR UPDATE SKIP LOCKED` + expiring leases
- workers never hold a DB transaction while fetching HTTP or writing ClickHouse
- if a worker dies, another worker can reclaim stations after `lease_until`
- if a lease is lost mid-iteration, guarded Postgres feedback prevents stale owner updates
- duplicate ClickHouse inserts are acceptable; reads must deduplicate immutable events

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
