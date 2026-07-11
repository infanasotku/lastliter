CREATE VIEW station_hourly_stats_v AS
SELECT station_id,
    toDayOfWeek(observed_at) AS weekday,
    toHour(observed_at) AS hour,
    count() AS observations_count,
    countIf(fuel_state = 'has_fuel') AS has_fuel_count,
    countIf(fuel_state = 'no_fuel') AS no_fuel_count,
    countIf(
        fuel_state = 'has_fuel'
        AND queue_severity IS NOT NULL
    ) AS queue_known_with_fuel_count,
    countIf(
        fuel_state = 'has_fuel'
        AND queue_severity > 0
    ) AS queue_with_fuel_count,
    countIf(
        fuel_state = 'has_fuel'
        AND queue_severity >= 3
    ) AS bad_queue_with_fuel_count,
    has_fuel_count / nullIf(observations_count, 0) AS fuel_available_ratio,
    queue_with_fuel_count / nullIf(queue_known_with_fuel_count, 0) AS queue_probability_when_known,
    bad_queue_with_fuel_count / nullIf(queue_known_with_fuel_count, 0) AS bad_queue_probability_when_known,
    avgIf(
        queue_severity,
        fuel_state = 'has_fuel'
        AND queue_severity IS NOT NULL
    ) AS avg_queue_severity_when_fuel,
    queue_known_with_fuel_count / nullIf(has_fuel_count, 0) AS queue_data_coverage_when_fuel
FROM lastliter_test.station_observations_normalized_v
GROUP BY station_id,
    weekday,
    hour;