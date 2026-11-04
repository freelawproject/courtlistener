"""Adapter and merge logic for the USPTO Patent Litigation Docket Reports.

The USPTO built PTLITIG from the same PACER docket reports that RECAP captures,
so a PTLITIG case is a flattened sibling of Juriscraper's ``DocketReport.data``.
Rather than write new normalization, we reshape each case into that dict and feed
it through the existing ``cl.recap.mergers`` primitives, exactly as the SCOTUS
and Texas importers do.
"""

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from asgiref.sync import async_to_sync
from django.db import transaction

from cl.recap.mergers import (
    add_parties_and_attorneys,
    find_docket_object,
    update_docket_metadata,
)
from cl.search.models import (
    Docket,
    DocketEntry,
    DocketIdentifier,
    RECAPDocument,
)

logger = logging.getLogger(__name__)

# PTLITIG's patent_doc_type values map one-to-one onto DocketIdentifier types.
# Rows with any other (or a blank) doc type carry no usable patent number and
# are skipped.
PATENT_DOC_TYPES = {
    "Patent": DocketIdentifier.PATENT,
    "Application": DocketIdentifier.APPLICATION,
    "Published Application": DocketIdentifier.PUBLISHED_APPLICATION,
    "Foreign Patent": DocketIdentifier.FOREIGN_PATENT,
}


def parse_date(value: str) -> date | None:
    """Parse a PTLITIG ISO date, returning None when it is blank or invalid."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def make_docket_data(
    case: dict[str, str], nature_of_suit: str
) -> dict[str, Any]:
    """Reshape a PTLITIG ``cases`` row into the dict update_docket_metadata wants."""
    return {
        "case_name": case["case_name"],
        "docket_number": case["case_number"],
        "pacer_case_id": case["pacer_id"] or None,
        "date_filed": parse_date(case["date_filed"]),
        "date_terminated": parse_date(case["date_closed"]),
        "date_last_filing": parse_date(case["date_last_filed"]),
        "cause": case["case_cause"],
        "nature_of_suit": nature_of_suit,
        "jury_demand": case["jury_demand"],
        "jurisdiction": case["jurisdictional_basis"],
        "assigned_to_str": case["assigned_to"],
        "referred_to_str": case["referred_to"],
    }


def make_party_list(
    name_rows: list[dict[str, str]], attorney_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Build the Juriscraper-style parties list from PTLITIG names + attorneys.

    PTLITIG stores one row per party in ``names`` and one row per attorney in
    ``attorneys``; the two are linked by ``party_row_count``. The PACER contact
    blob and semicolon-separated roles are passed through untouched so that
    ``add_parties_and_attorneys`` can normalize them the same way it does for
    RECAP uploads.
    """
    attorneys_by_party: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in attorney_rows:
        attorneys_by_party[row["party_row_count"]].append(
            {
                "name": row["attorney_name"],
                "contact": (row["attorney_contactinfo"] or "").replace(
                    "; ", "\n"
                ),
                "roles": [
                    role.strip()
                    for role in (row["position"] or "").split(";")
                    if role.strip()
                ],
            }
        )

    return [
        {
            "name": row["name"],
            "type": row["party_type"],
            "extra_info": "",
            "date_terminated": None,
            "attorneys": attorneys_by_party.get(row["party_row_count"], []),
        }
        for row in name_rows
    ]


def add_patent_identifiers(
    d: Docket, patent_rows: list[dict[str, str]]
) -> None:
    """Store the patents asserted in a case as DocketIdentifier rows.

    The patent number is kept exactly as found in the source; the
    (docket, type, value) unique constraint makes re-runs idempotent.
    """
    for row in patent_rows:
        value = (row["patent"] or "").strip()
        identifier_type = PATENT_DOC_TYPES.get(row["patent_doc_type"])
        if not value or value == "NA" or identifier_type is None:
            continue
        DocketIdentifier.objects.get_or_create(
            docket=d, type=identifier_type, value=value
        )


def add_ptlitig_docket_entries(
    d: Docket, document_rows: list[dict[str, str]]
) -> None:
    """Add PTLITIG docket entries to a docket without disturbing existing ones.

    - Numbered entries are matched on their entry number, so an entry is created
      only when that number isn't already present (a safe gap-fill against
      existing RECAP entries). Unlike ``add_docket_entries``, entries without a
      filing date are kept, since the number identifies them.
    - Unnumbered entries have no stable key to match on, so they are only added
      to dockets that start out with no entries at all. That sidesteps any
      merge/duplication question against RECAP, and is naturally idempotent: a
      re-run finds the entries from the previous run and adds nothing.

    A stub document is created for each newly created entry.
    """
    # Whether the docket had any entries before this import touched it; decided
    # up front so the numbered entries we add below don't change the answer.
    add_unnumbered = not d.docket_entries.exists()
    for row in document_rows:
        number = (row["doc_number"] or "").strip()
        if number.isdigit():
            entry, created = DocketEntry.objects.get_or_create(
                docket=d,
                entry_number=int(number),
                defaults={
                    "description": row["long_description"] or "",
                    "date_filed": parse_date(row["doc_date_filed"]),
                },
            )
            if not created:
                # Entry already existed; leave it and its documents untouched.
                continue
        elif add_unnumbered:
            entry = DocketEntry.objects.create(
                docket=d,
                entry_number=None,
                date_filed=parse_date(row["doc_date_filed"]),
                description=row["long_description"] or "",
            )
        else:
            # Unnumbered entry on a docket that already has entries; skip it.
            continue
        RECAPDocument.objects.create(
            docket_entry=entry,
            document_type=RECAPDocument.PACER_DOCUMENT,
            document_number=number if number.isdigit() else "",
            is_available=False,
            description=row["short_description"] or "",
        )


def merge_ptlitig_docket(
    case: dict[str, str],
    nature_of_suit: str,
    patent_rows: list[dict[str, str]],
    party_list: list[dict[str, Any]],
    document_rows: list[dict[str, str]] | None = None,
) -> Docket:
    """Merge a single PTLITIG case into CourtListener.

    Resolves (or creates) the docket with the same rule RECAP uses, updates its
    metadata, records the USPTO PTLITIG source, and stores the asserted patents.
    Parties are only added to dockets that don't already have any, so PTLITIG's
    thinner snapshot never overwrites richer RECAP data. Docket entries are a
    safe gap-fill (see ``add_ptlitig_docket_entries``), so they're added to any
    docket without touching the entries it already has.
    """
    with transaction.atomic():
        d = async_to_sync(find_docket_object)(
            court_id=case["district_id"],
            pacer_case_id=case["pacer_id"] or None,
            docket_number=case["case_number"],
            federal_defendant_number=None,
            federal_dn_judge_initials_assigned=None,
            federal_dn_judge_initials_referred=None,
            docket_source=Docket.USPTO_PTLITIG,
        )
        d = async_to_sync(update_docket_metadata)(
            d, make_docket_data(case, nature_of_suit)
        )
        d.add_uspto_ptlitig_source()
        d.save()

        if party_list and not d.parties.exists():
            add_parties_and_attorneys(d, party_list)
        if document_rows:
            add_ptlitig_docket_entries(d, document_rows)
        add_patent_identifiers(d, patent_rows)
    return d
