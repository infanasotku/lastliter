CREATE VIEW lastliter_test.station_observations_normalized_v AS WITH replaceAll(
    replaceAll(
        replaceAll(lowerUTF8(detail), '–', '-'),
        '—',
        '-'
    ),
    'ё',
    'е'
) AS normalized_detail
SELECT observation_id,
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
FROM lastliter_test.station_observations_raw;