CREATE TABLE station_observations_raw (
    observation_id UInt64,
    station_id String,
    observed_at DateTime64(3, 'UTC'),
    status LowCardinality(String),
    detail String,
    author_reliable Bool,
    on_site Bool,
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3),
    source LowCardinality(String) DEFAULT 'gdebenz'
) ENGINE = ReplacingMergeTree PARTITION BY toYYYYMM(observed_at)
ORDER BY (station_id, observed_at, observation_id);