"""Load a Court-PASS scrape run into CourtListener."""

import logging
import sqlite3
from typing import Any

from django.db.models import Model
from juriscraper.state.docket import DocketEntryType, DocketType, PartyType

from cl.corpus_importer.state.loader import JKentScrapeLoader, UnusableScrape
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

CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "asx": "video/x-ms-asf",
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
-- The archive row carries what only the download knows: the hash the
-- scraper took of the bytes, how many there were, and what kind of file it
-- asked for. It joins on the stored path, which the scraper names by
-- content and so never reuses for two files.
download AS (
    SELECT
        docket_number,
        file_index,
        local_path,
        content_hash,
        file_size,
        file_type
    FROM (
        SELECT
            json_extract(results.data_json, '$.docket_number') AS
                docket_number,
            json_extract(results.data_json, '$.file_index') AS file_index,
            json_extract(results.data_json, '$.local_path') AS local_path,
            COALESCE(archived_files.content_hash, '') AS content_hash,
            archived_files.file_size AS file_size,
            COALESCE(archived_files.expected_type, '') AS file_type,
            ROW_NUMBER() OVER (
                PARTITION BY
                    json_extract(results.data_json, '$.docket_number'),
                    json_extract(results.data_json, '$.file_index')
                ORDER BY results.id DESC
            ) AS attempt
        FROM results
        LEFT JOIN archived_files
            ON archived_files.file_path =
               json_extract(results.data_json, '$.local_path')
        WHERE results.result_type = 'NYCourtPassFile'
          AND json_extract(results.data_json, '$.docket_number') IS NOT NULL
          AND json_extract(results.data_json, '$.file_index') IS NOT NULL
          AND COALESCE(
                  json_extract(results.data_json, '$.local_path'), ''
              ) <> ''
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
            'local_path', COALESCE(download.local_path, ''),
            'content_hash', COALESCE(download.content_hash, ''),
            'file_size', download.file_size,
            -- Named by the scrape's vocabulary rather than as a MIME type,
            -- which `normalize` resolves; see `CONTENT_TYPES`.
            'file_type', COALESCE(download.file_type, '')
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
    ) AS payload,
    json_extract(docket.data_json, '$.no_files_for_case') AS no_files_for_case,
    COALESCE(json_array_length(docket.data_json, '$.files'), 0) AS file_count
FROM docket
LEFT JOIN entry ON entry.docket_id = docket.id
LEFT JOIN party ON party.docket_id = docket.id
LEFT JOIN issue ON issue.docket_id = docket.id
ORDER BY docket.docket_number
"""


class NYCoACourtPassLoader(JKentScrapeLoader[NYCoACase]):
    """Loads a Court-PASS run into CourtListener."""

    name = "nycoa"
    query = QUERY
    payload_column = "payload"
    scrape_model = NYCoACase
    merger: type[Merger[NYCoACase, None, Model]] = NYCoADocketMerger
    document_model = NYCoADocument

    @staticmethod
    def _refuse_unread_file_list(
        payload: dict[str, Any], row: sqlite3.Row
    ) -> None:
        """Refuse a docket whose filing detail page said nothing about files.

        If NYCourtPass doesn't produce either a notice saying there's no files
        or a list of files, then assume there's some html error and be noisy
        about it.

        :param payload: The docket payload, for naming the docket refused.
        :param row: The query row, read for the two columns `QUERY` selects
            alongside the payload.
        :raises UnusableScrape: If the page attested to neither.
        """
        if row["no_files_for_case"] == 1 or row["file_count"]:
            return
        raise UnusableScrape(
            f"{payload['docket_number']} states neither that it has no files "
            "nor any file its filing detail page listed, so its file list "
            "went unread and merging it would prune every document the "
            "docket has."
        )

    @staticmethod
    def _content_type(document: dict[str, Any]) -> str:
        """The MIME type to store and to serve a downloaded file under.

        :param document: One file of a filing, as `QUERY` shaped it.
        :return: The type, or the empty string
        """
        kind = document.get("file_type") or ""
        path = document.get("local_path") or ""
        if not kind or not path:
            return ""
        if not path.lower().endswith(f".{kind.lower()}"):
            logger.error(
                "Court-PASS file %s is stored at %s, which does not end in "
                "the %r the scrape calls it; serving it under no type.",
                document.get("file_name", ""),
                path,
                kind,
            )
            return ""
        if content_type := CONTENT_TYPES.get(kind.lower(), ""):
            return content_type
        logger.error(
            "Court-PASS file %s is a %r, which CONTENT_TYPES does not cover; "
            "serving it under no type.",
            document.get("file_name", ""),
            kind,
        )
        return ""

    def normalize(
        self, payload: dict[str, Any], row: sqlite3.Row
    ) -> dict[str, Any]:
        """Name the enum members `QUERY` has no way to state, resolve each
        file's MIME type, and refuse a docket whose file list did not parse.

        :raises UnusableScrape: For a docket whose filing detail page carried
            neither the Court's "no files available for this case" line nor a
            file table the scraper could read. See `_refuse_unread_file_list`.
        """
        self._refuse_unread_file_list(payload, row)
        payload["docket_type"] = DocketType.UNKNOWN
        for entry in payload["entries"]:
            entry["entry_type"] = DocketEntryType.UNKNOWN
            for document in entry["attachments"]:
                document["content_type"] = self._content_type(document)
        for party in payload["parties"]:
            role = party["party_role_raw"]
            party["party_type"] = PARTY_TYPES.get(
                role.lower(),
                PartyType.UNASSIGNED if role else PartyType.UNKNOWN,
            )
        return payload
