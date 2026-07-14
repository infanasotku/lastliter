CREATE OR REPLACE VIEW station_observations_normalized_v AS WITH replaceAll(
        replaceAll(
            replaceAll(lowerUTF8(detail), '–', '-'),
            '—',
            '-'
        ),
        'ё',
        'е'
    ) AS normalized_detail,
    multiIf(
        positionCaseInsensitiveUTF8(normalized_detail, 'заправка не работает') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'не работает') > 0,
        'station_closed',
        positionCaseInsensitiveUTF8(normalized_detail, 'перерыв более 2 ч') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'перерыв более 2ч') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'перерыв больше 2 ч') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'перерыв больше 2ч') > 0,
        'break_gt_2h',
        positionCaseInsensitiveUTF8(normalized_detail, 'перерыв 1-2 ч') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'перерыв 1-2ч') > 0,
        'break_1_2h',
        positionCaseInsensitiveUTF8(normalized_detail, 'перерыв до 1 ч') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'перерыв до 1ч') > 0,
        'break_lt_1h',
        positionCaseInsensitiveUTF8(normalized_detail, 'перерыв') > 0,
        'break_unknown',
        'available'
    ) AS service_state
SELECT observation_id,
    station_id,
    observed_at,
    multiIf(
        service_state IN (
            'station_closed',
            'break_gt_2h',
            'break_1_2h',
            'break_unknown'
        ),
        'no_fuel',
        status IN ('yes', 'queue', 'low'),
        'has_fuel',
        status = 'no',
        'no_fuel',
        'unknown'
    ) AS fuel_state,
    service_state,
    multiIf(
        positionCaseInsensitiveUTF8(normalized_detail, 'без очереди') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'очереди нет') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'нет очереди') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'свободно') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'пусто') > 0,
        0,
        positionCaseInsensitiveUTF8(normalized_detail, '100+') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, '100 +') > 0
        OR match(normalized_detail, '100\\s*\\+'),
        6,
        positionCaseInsensitiveUTF8(normalized_detail, '50-100') > 0,
        5,
        positionCaseInsensitiveUTF8(normalized_detail, '50+') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, '50 +') > 0
        OR match(normalized_detail, '50\\s*\\+'),
        4,
        positionCaseInsensitiveUTF8(normalized_detail, '20-50') > 0,
        3,
        positionCaseInsensitiveUTF8(normalized_detail, '5-20') > 0,
        2,
        positionCaseInsensitiveUTF8(normalized_detail, 'до 5 машин') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'до 5') > 0,
        1,
        positionCaseInsensitiveUTF8(normalized_detail, 'большая очередь') > 0,
        4,
        positionCaseInsensitiveUTF8(normalized_detail, 'очеред') > 0
        OR positionCaseInsensitiveUTF8(normalized_detail, 'машин') > 0,
        2,
        NULL
    ) AS queue_severity,
    author_reliable,
    on_site
FROM station_observations_raw;
--
CREATE OR REPLACE VIEW station_hourly_stats_v AS
SELECT station_id,
    toDayOfWeek(observed_at) AS weekday,
    toHour(observed_at) AS hour,
    count() AS observations_count,
    countIf(fuel_state = 'has_fuel') AS has_fuel_count,
    countIf(fuel_state = 'no_fuel') AS no_fuel_count,
    countIf(fuel_state = 'unknown') AS unknown_fuel_count,
    countIf(
        service_state IN (
            'station_closed',
            'break_unknown',
            'break_1_2h',
            'break_gt_2h'
        )
    ) AS service_unavailable_count,
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
    countIf(
        fuel_state = 'has_fuel'
        AND queue_severity >= 5
    ) AS very_bad_queue_with_fuel_count,
    avgIf(
        queue_severity,
        fuel_state = 'has_fuel'
        AND queue_severity IS NOT NULL
    ) AS avg_queue_severity_when_fuel,
    maxIf(
        queue_severity,
        fuel_state = 'has_fuel'
        AND queue_severity IS NOT NULL
    ) AS max_queue_severity_when_fuel,
    has_fuel_count / nullIf(observations_count, 0) AS fuel_available_ratio,
    no_fuel_count / nullIf(observations_count, 0) AS no_fuel_ratio,
    unknown_fuel_count / nullIf(observations_count, 0) AS unknown_fuel_ratio,
    service_unavailable_count / nullIf(observations_count, 0) AS service_unavailable_ratio,
    queue_known_with_fuel_count / nullIf(has_fuel_count, 0) AS queue_data_coverage_when_fuel,
    queue_with_fuel_count / nullIf(queue_known_with_fuel_count, 0) AS queue_probability_when_known,
    bad_queue_with_fuel_count / nullIf(queue_known_with_fuel_count, 0) AS bad_queue_probability_when_known,
    very_bad_queue_with_fuel_count / nullIf(queue_known_with_fuel_count, 0) AS very_bad_queue_probability_when_known
FROM station_observations_normalized_v
GROUP BY station_id,
    weekday,
    hour;