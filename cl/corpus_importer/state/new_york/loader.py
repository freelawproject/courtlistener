"""Load a Court-PASS scrape run into CourtListener."""

import logging
import sqlite3
from typing import Any

from django.db.models import Model
from juriscraper.state.docket import DocketEntryType, DocketType, PartyType

from cl.corpus_importer.state.loader import JKentScrapeLoader
from cl.corpus_importer.state.merger import Merger
from cl.corpus_importer.state.new_york.mergers import NYCoADocketMerger
from cl.corpus_importer.state.new_york.nycourts_gov import NYCoACase
from cl.search.state.new_york.models import NYCoADocument

logger = logging.getLogger(__name__)

PARTY_TYPES: dict[str, PartyType] = {
    "appellant": PartyType.APPELLANT,
    "appellee": PartyType.APPELLEE,
    "petitioner": PartyType.PETITIONER,
    "respondent": PartyType.RESPONDENT,
}

#: One finished docket payload per row, in the standard docket format.
QUERY = """
WITH scraped AS (
    SELECT
        id,
        data_json,
        json_extract(data_json, '$.docket_number') AS docket_number
    FROM results
    WHERE result_type = 'NYCourtPassDocket'
      AND is_valid = 1
      AND COALESCE(json_extract(data_json, '$.docket_number'), '') <> ''
      AND (
          json_extract(data_json, '$.no_files_for_case') = 1
          OR COALESCE(json_array_length(data_json, '$.files'), 0) > 0
      )
),
docket AS (
    SELECT id, data_json, docket_number
    FROM (
        SELECT
            id,
            data_json,
            docket_number,
            ROW_NUMBER() OVER (
                PARTITION BY docket_number ORDER BY id
            ) AS grid_position
        FROM scraped
    )
    WHERE grid_position = 1 -- deduplicate dockets
),
download AS (
    SELECT docket_number, file_index, local_path
    FROM (
        SELECT
            json_extract(data_json, '$.docket_number') AS docket_number,
            json_extract(data_json, '$.file_index') AS file_index,
            json_extract(data_json, '$.local_path') AS local_path,
            ROW_NUMBER() OVER (
                PARTITION BY
                    json_extract(data_json, '$.docket_number'),
                    json_extract(data_json, '$.file_index')
                ORDER BY id DESC
            ) AS attempt
        FROM results
        WHERE result_type = 'NYCourtPassFile'
          AND json_extract(data_json, '$.docket_number') IS NOT NULL
          AND json_extract(data_json, '$.file_index') IS NOT NULL
          AND COALESCE(json_extract(data_json, '$.local_path'), '') <> ''
    )
    WHERE attempt = 1
),
file AS (
    SELECT
        docket.id AS docket_id,
        json_extract(item.value, '$.docket_entry_id') AS docket_entry_id,
        item.key AS listing,
        json_object(
            'file_name', COALESCE(json_extract(item.value, '$.file_name'), ''),
            'available', COALESCE(json_extract(item.value, '$.available'), 1),
            'doc_role', json_extract(item.value, '$.doc_role'),
            'doc_party', COALESCE(json_extract(item.value, '$.doc_party'), ''),
            'doc_type', json_extract(item.value, '$.doc_type'),
            'volume', json_extract(item.value, '$.volume'),
            'part', json_extract(item.value, '$.part'),
            'local_path', COALESCE(download.local_path, '')
        ) AS document,
        ROW_NUMBER() OVER (
            PARTITION BY
                docket.id,
                json_extract(item.value, '$.docket_entry_id'),
                COALESCE(json_extract(item.value, '$.file_name'), '')
            ORDER BY
                COALESCE(json_extract(item.value, '$.available'), 1) DESC,
                item.key
        ) AS copy
    FROM docket
    JOIN json_each(docket.data_json, '$.files') AS item
    LEFT JOIN download
        ON download.docket_number = docket.docket_number
       AND download.file_index = json_extract(item.value, '$.file_index')
    WHERE COALESCE(json_extract(item.value, '$.docket_entry_id'), '') <> ''
),
attachment AS (
    SELECT
        docket_id,
        docket_entry_id,
        json_group_array(json(document) ORDER BY listing) AS documents
    FROM file
    WHERE copy = 1
    GROUP BY docket_id, docket_entry_id
),
entry AS (
    SELECT
        docket.id AS docket_id,
        json_group_array(
            json_object(
                'docket_entry_id',
                json_extract(item.value, '$.docket_entry_id'),
                'entry_index', json_extract(item.value, '$.entry_index'),
                'raw_filing_type',
                COALESCE(json_extract(item.value, '$.raw_filing_type'), ''),
                'entry_filing_type',
                json_extract(item.value, '$.entry_filing_type'),
                'party', COALESCE(json_extract(item.value, '$.party'), ''),
                'date_filed', json_extract(item.value, '$.date_received'),
                'date_due', json_extract(item.value, '$.date_due'),
                'entry_role', json_extract(item.value, '$.entry_role'),
                'entry_doctype', json_extract(item.value, '$.entry_doctype'),
                'attachments', json(COALESCE(attachment.documents, '[]'))
            )
            ORDER BY item.key
        ) AS entries,
        MIN(NULLIF(json_extract(item.value, '$.date_received'), '')) AS
            date_filed
    FROM docket
    JOIN json_each(docket.data_json, '$.docket_entries') AS item
    LEFT JOIN attachment
        ON attachment.docket_id = docket.id
       AND attachment.docket_entry_id =
           json_extract(item.value, '$.docket_entry_id')
    WHERE COALESCE(json_extract(item.value, '$.docket_entry_id'), '') <> ''
    GROUP BY docket.id
),
attorney AS (
    SELECT
        docket.id AS docket_id,
        item.key AS listing,
        TRIM(COALESCE(json_extract(item.value, '$.party_name'), '')) AS
            party_name,
        TRIM(COALESCE(json_extract(item.value, '$.party_role'), '')) AS
            party_role,
        TRIM(COALESCE(json_extract(item.value, '$.attorney_name'), '')) AS
            attorney_name,
        COALESCE(json_extract(item.value, '$.firm'), '') AS firm,
        COALESCE(json_extract(item.value, '$.address'), '') AS address,
        COALESCE(json_extract(item.value, '$.phone'), '') AS phone
    FROM docket
    JOIN json_each(docket.data_json, '$.attorneys') AS item
    WHERE TRIM(COALESCE(json_extract(item.value, '$.party_name'), '')) <> ''
),
contact AS (
    SELECT docket_id, attorney_name, firm, address, phone
    FROM (
        SELECT
            docket_id,
            attorney_name,
            firm,
            address,
            phone,
            ROW_NUMBER() OVER (
                PARTITION BY docket_id, attorney_name ORDER BY listing
            ) AS appearance
        FROM attorney
        WHERE attorney_name <> ''
    )
    WHERE appearance = 1
),
representative AS (
    SELECT
        attorney.docket_id,
        attorney.party_name,
        attorney.party_role,
        json_group_array(
            json_object(
                'name', attorney.attorney_name,
                'firm', contact.firm,
                'address', contact.address,
                'phone', contact.phone
            )
            ORDER BY attorney.listing
        ) AS representatives
    FROM attorney
    JOIN contact
        ON contact.docket_id = attorney.docket_id
       AND contact.attorney_name = attorney.attorney_name
    WHERE attorney.attorney_name <> ''
    GROUP BY attorney.docket_id, attorney.party_name, attorney.party_role
),
party AS (
    SELECT
        grouped.docket_id,
        json_group_array(
            json_object(
                'name', grouped.party_name,
                'party_role_raw', grouped.party_role,
                'representatives',
                json(COALESCE(representative.representatives, '[]'))
            )
            ORDER BY grouped.listing
        ) AS parties
    FROM (
        SELECT docket_id, party_name, party_role, MIN(listing) AS listing
        FROM attorney
        GROUP BY docket_id, party_name, party_role
    ) AS grouped
    LEFT JOIN representative
        ON representative.docket_id = grouped.docket_id
       AND representative.party_name = grouped.party_name
       AND representative.party_role = grouped.party_role
    GROUP BY grouped.docket_id
),
issue AS (
    SELECT
        docket.id AS docket_id,
        json_group_array(
            json_object(
                'category_raw',
                COALESCE(json_extract(item.value, '$.category_raw'), ''),
                'category', json_extract(item.value, '$.category'),
                'subcategory', json_extract(item.value, '$.subcategory'),
                'detail', COALESCE(json_extract(item.value, '$.detail'), '')
            )
            ORDER BY item.key
        ) AS issues
    FROM docket
    JOIN json_each(docket.data_json, '$.issues') AS item
    WHERE item.type = 'object'
    GROUP BY docket.id
)
SELECT
    json_object(
        'court_id', COALESCE(json_extract(docket.data_json, '$.court'), ''),
        'docket_number', docket.docket_number,
        'case_name',
        COALESCE(json_extract(docket.data_json, '$.case_name'), ''),
        'case_name_full',
        COALESCE(json_extract(docket.data_json, '$.case_name'), ''),
        'case_name_short',
        COALESCE(json_extract(docket.data_json, '$.case_short_name'), ''),
        'date_filed', entry.date_filed,
        'argument_date', json_extract(docket.data_json, '$.argument_date'),
        'decision_date', json_extract(docket.data_json, '$.decision_date'),
        'official_citation',
        COALESCE(json_extract(docket.data_json, '$.official_citation'), ''),
        'lower_court_citation',
        COALESCE(json_extract(docket.data_json, '$.lower_court_citation'), ''),
        'issues', json(COALESCE(issue.issues, '[]')),
        'entries', json(COALESCE(entry.entries, '[]')),
        'parties', json(COALESCE(party.parties, '[]')),
        'transfers', json_array()
    ) AS payload
FROM docket
LEFT JOIN entry ON entry.docket_id = docket.id
LEFT JOIN party ON party.docket_id = docket.id
LEFT JOIN issue ON issue.docket_id = docket.id
ORDER BY docket.docket_number
"""


class NYCoACourtPassLoader(JKentScrapeLoader[NYCoACase]):
    """Loads a Court-PASS run into CourtListener."""

    query = QUERY
    payload_column = "payload"
    scrape_model = NYCoACase
    merger: type[Merger[NYCoACase, None, Model]] = NYCoADocketMerger
    document_model = NYCoADocument

    def normalize(
        self, payload: dict[str, Any], row: sqlite3.Row
    ) -> dict[str, Any]:
        """Name the enum members `QUERY` has no way to state.

        The payload arrives finished apart from these three, each of which
        stands for something Court-PASS does not state at all: it types neither
        the case nor its filings in the cross-state vocabulary, and it states a
        party's role in words that only sometimes name a `PartyType` member.
        """
        payload["docket_type"] = DocketType.UNKNOWN
        for entry in payload["entries"]:
            entry["entry_type"] = DocketEntryType.UNKNOWN
        for party in payload["parties"]:
            role = party["party_role_raw"]
            party["party_type"] = PARTY_TYPES.get(
                role.lower(),
                PartyType.UNASSIGNED if role else PartyType.UNKNOWN,
            )
        return payload
