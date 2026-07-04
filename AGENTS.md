# AGENTS.md — lastliter

## 🧠 Project Overview

lastliter is a geospatial + temporal analytics service for fuel stations.

The core goal of the system is:

> Predict the optimal time to visit a fuel station to minimize waiting time and avoid queues or fuel unavailability.

This is NOT a real-time map app.
This is a historical + predictive analytics system based on crowd-sourced observations.

---

## 🎯 Product Goal

The main user question:

> "When should I go to this specific gas station to avoid queues?"

The system should answer:

- Best time windows (hour/day of week)
- Worst time windows
- Current probability of queue or fuel availability
- Confidence level of prediction

---

## 📊 Available Data Sources

We aggregate data from `gdebenz.ru` APIs.

---

### 1. Station Registry (`/api/stations`)

Static reference data about fuel stations.

Contains:

- station id (OSM-based)
- name
- brand
- location (lat/lon)
- address
- available fuel types
- basic status flags

Purpose:

- entity resolution (station identity)
- geospatial indexing
- joining key for all other datasets

---

### 2. Nearby Snapshot (`/api/nearby`)

Geospatial real-time snapshot relative to a user query.

Contains:

- station status (yes / no / queue / low)
- distance to user
- fuel availability
- confidence signals
- confirmations count
- last update timestamp

Purpose:

- UI layer (map view)
- "what is happening right now"
- low-latency state representation

IMPORTANT:
This is NOT historical data.
It is a query-time projection.

---

### 3. Station Comments Summary (`/api/comments/{station_id}`)

Aggregated station-level state.

Contains:

- current status
- confirmations (total / fresh)
- fuel availability snapshot
- confidence base score
- conflict signals
- metadata

Purpose:

- current state estimation of a station
- input for reliability scoring
- normalization layer for noisy reports

---

### 4. Station Event History (`/api/comments/{station_id}/recent`)

Time-ordered event stream per station.

Each event contains:

- status (yes / no / queue / low)
- timestamp (created_at)
- author reliability flag
- on-site indicator
- textual detail (free-form)

Purpose:

- core dataset for analytics
- time-series modeling
- detection of:
  - queue duration
  - fuel outage cycles
  - state transitions

This is the MOST IMPORTANT dataset for predictive modeling.

---

## 🧱 Data Model Concept

We treat the system as:

### Dimension table:

- stations

### Fact/event stream:

- station_events (directly from `/api/comments/{station_id}/recent`)

IMPORTANT:
There is no intermediate normalization layer between raw events and analytics.

---

## 🔄 Key Concept: State Transitions

We model station behavior as state changes over time:

Possible states:

- `available`
- `low_fuel`
- `queue`
- `no_fuel`

Transitions are derived directly from event history.

Example:

- available → queue → available
- available → low → no → available

These transitions are used to compute:

- duration distributions
- frequency of congestion
- time-based patterns

---

## 📈 Core Metrics

For each station + weekday + hour:

- queue_probability
- fuel_unavailability_probability
- average_event_duration
- confidence_score
- sample_count

---

## 🧠 Prediction Strategy (MVP)

No ML required initially.

We use:

- historical aggregation
- weighted probabilities
- recency decay
- confidence scoring based on sample size

Scoring idea:

- availability weight: +0.6
- queue penalty: -0.3
- freshness: +0.1

---

## 🏗️ Storage (ClickHouse)

ClickHouse is used as the main analytics engine.

Expected tables:

### stations

Static dimension table

### station_events

Raw normalized events from `/api/comments/{station_id}/recent`

Fields:

- station_id
- timestamp
- status
- author_reliable
- on_site
- raw_detail

### station_hourly_aggregates

Precomputed stats per:

- station_id
- weekday
- hour

---

## ⚠️ Data Quality Notes

- User-generated data is noisy
- Some authors are unreliable
- Reports may contradict each other
- Some stations have sparse data

Therefore:

- Always compute confidence score
- Always expose data sparsity
- Never present predictions as absolute truth

---

## 🧩 System Components

### 1. Collector

- Fetches API data periodically
- Normalizes events (no intermediate event layer)
- Writes directly to ClickHouse

### 2. Analytics layer

- Aggregations (hour/day patterns)
- State transition extraction
- Confidence scoring

### 3. API service

- Provides:
  - station prediction
  - heatmaps
  - current state
  - best time windows

### 4. Frontend (optional MVP)

- Map view
- Station card
- Time recommendation view

---

## 🧪 Important Design Principle

This project prioritizes:

> uncertainty-aware recommendation

Not:

> fake precision

If data is insufficient:

- explicitly say so
- reduce confidence
- avoid overfitting patterns

---

## 🚀 Definition of Done (MVP)

MVP is complete when:

- historical data is collected for ≥ 30 days
- hourly patterns can be computed per station
- system can output:
  - best 2–3 time windows per station
  - worst time windows
  - confidence score

---

## 🧠 Mental Model for Agents

When working on this project, always think:

- What is the state of a station over time?
- What transitions happened before and after congestion?
- How reliable is this observation?
- What pattern repeats weekly?

NOT:

- just latest snapshot
- just map rendering
- just storing API responses
