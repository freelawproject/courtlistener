-- ---------------------------------------------------------------------------
-- NYCoA Court-PASS kent-run loader.
--
-- Produces one row per logical docket, with the full aggregate tree
-- encoded as a single ``scrape_json`` TEXT column. The merger's
-- ``normalize`` pass parses the JSON and feeds it to Pydantic.
--
-- Conventions:
--   * Empty TEXT fields are returned as '' so Django's ``TextField(blank=True)``
--     accepts them on insert.
--   * Dates are returned as ISO ``YYYY-MM-DD`` strings; Pydantic parses them.
--   * ``court_id`` is hard-coded ``"ny"`` — this loader is NYCoA-only.
--   * ``temp_case_id`` is the scraper-internal UUID used to join docket /
--     file rows in this query; it is never surfaced to CL.
--   * Invalid (``is_valid=0``) docket rows are excluded — only
--     fully-confirmed dockets flow through.
--   * Court-PASS oral-argument recordings (.wmv) live behind a separate
--     HTTP host and are filtered out at the file stage by the
--     ``available = 1 AND local_path IS NOT NULL`` predicate.
-- ---------------------------------------------------------------------------


-- 1. NYCourtPassDocket rows — the single source of truth per docket.
-- Carries docket-detail-page data (FILINGS, attorneys) plus the
-- case-level scalars (case_name, case_short_name, argument_date,
-- decision_date) inline. ``files`` is also embedded on the docket but
-- has ``local_path = NULL``; we join against the separate
-- ``NYCourtPassFile`` rows below for the resolved S3 keys.
WITH valid_dockets AS (
    SELECT
        json_extract(data_json, '$.temp_case_id')         AS temp_case_id,
        json_extract(data_json, '$.docket_number')        AS docket_number,
        json_extract(data_json, '$.case_name')            AS case_name,
        json_extract(data_json, '$.case_short_name')      AS case_name_short,
        json_extract(data_json, '$.argument_date')        AS date_argued,
        json_extract(data_json, '$.decision_date')        AS date_filed,
        data_json                                         AS dj,
        created_at                                        AS scraped_at
    FROM results
    WHERE result_type = 'NYCourtPassDocket'
      AND is_valid = 1
      AND json_extract(data_json, '$.docket_number') IS NOT NULL
),

-- 2. NYCourtPassFile rows — scraped downloadable files. The embedded
-- ``files`` array on NYCourtPassDocket has ``local_path = NULL``; the
-- standalone NYCourtPassFile rows carry the resolved S3 key.
valid_files AS (
    SELECT
        json_extract(data_json, '$.temp_case_id')         AS temp_case_id,
        json_extract(data_json, '$.file_index')           AS file_index,
        json_extract(data_json, '$.file_name')            AS file_name,
        json_extract(data_json, '$.local_path')           AS local_path
    FROM results
    WHERE result_type = 'NYCourtPassFile'
      AND is_valid = 1
      AND json_extract(data_json, '$.available') = 1
      AND json_extract(data_json, '$.local_path') IS NOT NULL
),

-- 3. FILINGS-derived entries per docket: walk the docket_entries array
-- and prefix sequence_number with the ISO date for stable ordering.
filings_entries AS (
    SELECT
        d.temp_case_id,
        json_group_array(
            json_object(
                'sequence_number',
                printf(
                    '%s.%03d',
                    COALESCE(json_extract(je.value, '$.date_received'), '0000-00-00'),
                    je.key
                ),
                'date_filed',     json_extract(je.value, '$.date_received'),
                'filing_type',    COALESCE(json_extract(je.value, '$.filing_type'), ''),
                'description',    TRIM(
                    COALESCE(json_extract(je.value, '$.filing_type'), '')
                    || CASE
                         WHEN json_extract(je.value, '$.party') IS NOT NULL
                              AND json_extract(je.value, '$.party') != ''
                         THEN ' — ' || json_extract(je.value, '$.party')
                         ELSE ''
                       END
                ),
                'party_side',     COALESCE(json_extract(je.value, '$.party'), '')
            )
        ) AS entries_json
    FROM valid_dockets d, json_each(d.dj, '$.docket_entries') je
    GROUP BY d.temp_case_id
),

-- 4. File-only entries per docket: one synthesized DocketEntry per
-- NYCourtPassFile, sequence_number prefixed with "file." to keep the
-- bucket disjoint from FILINGS entries.
file_entries AS (
    SELECT
        f.temp_case_id,
        json_group_array(
            json_object(
                'sequence_number', printf('file.%03d', f.file_index),
                'date_filed',      NULL,
                'filing_type',     '',
                'description',     COALESCE(f.file_name, ''),
                'party_side',      '',
                'nycoadocument',   json_object(
                    'file_name',      COALESCE(f.file_name, ''),
                    'file_index',     f.file_index,
                    'filepath_local', f.local_path
                )
            )
        ) AS entries_json
    FROM valid_files f
    GROUP BY f.temp_case_id
),

-- 5. Attorneys per docket — flatten the attorneys[] array. The driver
-- splits each row into PartyType + Role + AttorneyOrgAssociation. We
-- pass the raw array through and let the normalize pass do the
-- restructuring (easier in Python than SQL).
attorneys_per_docket AS (
    SELECT
        d.temp_case_id,
        json_group_array(
            json_object(
                'party_name',      json_extract(att.value, '$.party_name'),
                'party_role',      json_extract(att.value, '$.party_role'),
                'firm',            json_extract(att.value, '$.firm'),
                'attorney_name',   json_extract(att.value, '$.attorney_name'),
                'address',         json_extract(att.value, '$.address'),
                'phone',           json_extract(att.value, '$.phone')
            )
        ) AS attorneys_json
    FROM valid_dockets d, json_each(d.dj, '$.attorneys') att
    GROUP BY d.temp_case_id
)

-- 6. Compose: one row per docket, with the full aggregate tree as JSON.
-- ``json()`` wraps the substring args so SQLite returns them as a
-- proper JSON value (not a quoted string) inside the outer object.
SELECT
    json_object(
        'court_id',          'ny',
        'docket_number',     d.docket_number,
        'docket_number_raw', d.docket_number,
        'case_name',         COALESCE(d.case_name, ''),
        'case_name_short',   COALESCE(d.case_name_short, ''),
        'case_name_full',    COALESCE(d.case_name, ''),
        'date_argued',       d.date_argued,
        'date_filed',        d.date_filed,
        'filings_entries',   json(COALESCE(fe.entries_json,  '[]')),
        'file_entries',      json(COALESCE(fle.entries_json, '[]')),
        'attorneys',         json(COALESCE(ad.attorneys_json, '[]'))
    ) AS scrape_json
FROM valid_dockets d
LEFT JOIN filings_entries    fe  ON fe.temp_case_id  = d.temp_case_id
LEFT JOIN file_entries       fle ON fle.temp_case_id = d.temp_case_id
LEFT JOIN attorneys_per_docket ad ON ad.temp_case_id = d.temp_case_id
ORDER BY d.docket_number;
