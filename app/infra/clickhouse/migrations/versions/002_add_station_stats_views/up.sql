CREATE VIEW station_observations_normalized_v AS
WITH replaceAll(
    replaceAll(
        replaceAll(lowerUTF8(detail), '–', '-'),
        '—',
        '-'
    ),
    'ё',
    'е'
) AS normalized_detail
SELECT
    observation_id,
    station_id,
    observed_at,
    multiIf(
        status IN ('yes', 'queue', 'low'),
        'has_fuel',
        status = 'no',
        'no_fuel',
        'unknown'
    ) AS fuel_state,
    multiIf(
        positionCaseInsensitiveUTF8(normalized_detail, 'без очереди') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'очереди нет') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'нет очереди') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'свободно') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'пусто') > 0,
        0,
        positionCaseInsensitiveUTF8(normalized_detail, '50+') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, '50 +') > 0,
        4,
        positionCaseInsensitiveUTF8(normalized_detail, '20-50') > 0,
        3,
        positionCaseInsensitiveUTF8(normalized_detail, '5-20') > 0,
        2,
        positionCaseInsensitiveUTF8(normalized_detail, 'очеред') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'машин') > 0,
        1,
        NULL
    ) AS queue_severity,
    author_reliable,
    on_site
FROM station_observations_raw;

CREATE VIEW station_hourly_stats_v AS
SELECT
    station_id,
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
    queue_known_with_fuel_count / nullIf(has_fuel_count, 0) AS queue_data_coverage_when_fuel,
    bad_queue_with_fuel_count / nullIf(queue_known_with_fuel_count, 0) AS bad_queue_probability_when_known,
    avgIf(
        queue_severity,
        fuel_state = 'has_fuel'
        AND queue_severity IS NOT NULL
    ) AS avg_queue_severity_when_fuel
FROM station_observations_normalized_v
GROUP BY
    station_id,
    weekday,
    hour;
