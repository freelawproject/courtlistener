"""Driver: translate a Juriscraper SCOTUS docket report dict into a
``ScotusDocket`` scrape and run it through the merger framework.

Replaces the legacy ``cl.corpus_importer.tasks.merge_scotus_docket``
flow. Responsibilities split exactly as in the Texas driver:

- **Driver**: everything that touches Juriscraper-shaped data or
  requires DB pre-resolution — court lookups, party/attorney
  normalization, lifecycle data shape conversion, QP URL resolution.
- **Schema layer** (:mod:`cl.scrapers.mergers.federal.scotus.scotus`):
  declarative tree the framework consumes (NKs, strategies, hooks).

Public entry point: :func:`merge_scotus_docket`. Returns the
framework's ``MergeOutcome`` so callers can iterate
``outcome.follow_ups`` (QP PDF download chain + per-document
download/extract chains). The ``download_file=False`` knob strips
document follow-ups from the returned outcome; the QP follow-up
honors the same flag for consistency with the legacy
``download_qp`` return value.

No disaggregation analog — SCOTUS is a single fixed court, so the
framework's NK lookup ``(court, docket_number)`` is sufficient.
"""

import logging
from typing import Any
from urllib.parse import urljoin

from django.db import transaction

from cl.corpus_importer.utils import create_docket_entry_sequence_numbers
from cl.lib.courts import find_court_object_by_name
from cl.lib.pacer import (
    normalize_attorney_contact,
    normalize_attorney_role,
)
from cl.people_db.models import Role
from cl.recap.mergers import normalize_long_description
from cl.scrapers.mergers import MergeOutcome, merge_one
from cl.scrapers.mergers.federal.scotus.scotus import (
    ScotusAttorneyOrgAssociationSchema,
    ScotusAttorneyOrgRef,
    ScotusAttorneyRef,
    ScotusDocket,
    ScotusDocketEntrySchema,
    ScotusDocketMetadataSchema,
    ScotusDocumentSchema,
    ScotusOCISchema,
    ScotusPartyRef,
    ScotusPartyTypeSchema,
    ScotusRoleSchema,
)
from cl.search.models import Court, Docket

logger = logging.getLogger(__name__)


_FOLLOWUP_DOWNLOAD = "scotus-document-download-and-extract"
_SCOTUS_BASE_URL = "https://www.supremecourt.gov/"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def merge_scotus_docket(
    report_data: dict[str, Any],
    *,
    using: str = "default",
    download_file: bool = True,
) -> MergeOutcome:
    """Merge a SCOTUS docket report into CourtListener.

    :param report_data: Parsed Juriscraper SCOTUS docket-report dict
        (see ``juriscraper/scotus/scotus_docket_report.py`` for the
        shape).
    :param using: Django database alias.
    :param download_file: When ``False``, document-download follow-ups
        and the QP-download follow-up are stripped from the returned
        outcome (the caller won't dispatch them).
    :raises ValueError: if the report dict is missing ``docket_number``.
    """
    docket_number = report_data.get("docket_number")
    if not docket_number:
        raise ValueError(
            "Docket number can't be missing in SCOTUS dockets."
        )
    logger.info("Merging SCOTUS docket %s", docket_number)

    court = Court.objects.using(using).get(pk="scotus")

    with transaction.atomic(using=using):
        scrape = _build_scotus_docket_scrape(report_data, court=court)
        outcome = merge_one(scrape, using=using)

    if not download_file:
        outcome = MergeOutcome(
            root=outcome.root,
            creates=outcome.creates,
            updates=outcome.updates,
            deletes=outcome.deletes,
            follow_ups=[
                fu
                for fu in outcome.follow_ups
                if getattr(fu, "name", None)
                not in (_FOLLOWUP_DOWNLOAD, "scotus-qp-download")
            ],
        )
    return outcome


# ---------------------------------------------------------------------------
# Top-level schema construction
# ---------------------------------------------------------------------------


def _build_scotus_docket_scrape(
    report_data: dict[str, Any], *, court: Court
) -> ScotusDocket:
    """Construct the full ``ScotusDocket`` scrape tree from the
    Juriscraper report dict. Pre-resolution + Juriscraper-shape
    translation happens here.

    Convention reminder: anywhere the source returned a falsy value
    that means "no data," we coerce to ``None`` so the
    ``ScrapeWinsIfPresent`` strategies don't clobber a real DB value
    with an empty string / falsy stand-in.
    """
    docket_number = report_data["docket_number"]
    case_name = _none_if_blank(report_data.get("case_name"))
    date_filed = report_data.get("date_filed")
    lower_court_name = _none_if_blank(report_data.get("lower_court"))

    appeal_from = None
    if lower_court_name:
        appeal_from = find_court_object_by_name(
            lower_court_name, bankruptcy=False
        )

    oci = _build_oci(report_data)
    metadata = _build_metadata(report_data)
    entries = _build_entries(report_data)
    party_types, role_set, org_assocs = _build_parties_attorneys_orgs(
        report_data.get("parties") or []
    )

    return ScotusDocket(
        court=court,
        docket_number=docket_number,
        docket_number_raw=docket_number,
        case_name=case_name,
        date_filed=date_filed,
        appeal_from=appeal_from,
        appeal_from_str=lower_court_name,
        source=Docket.SCRAPER,
        originating_court_information=oci,
        scotus_metadata=metadata,
        scotusdocketentry_set=entries,
        party_types=party_types,
        role_set=role_set,
        attorneyorganizationassociation_set=org_assocs,
    )


# ---------------------------------------------------------------------------
# OriginatingCourtInformation
# ---------------------------------------------------------------------------


def _build_oci(report_data: dict[str, Any]) -> ScotusOCISchema | None:
    """Return an OCI schema iff the scrape has at least one
    lower-court field populated; otherwise ``None`` so the framework
    (with the field's ``Union`` strategy) leaves any existing OCI
    untouched.

    Ports the legacy condition:
    ``if lower_court_case_numbers or lower_court_decision_date or
    lower_court_rehearing_denied_date``.
    """
    case_numbers = report_data.get("lower_court_case_numbers")
    case_numbers_raw = report_data.get("lower_court_case_numbers_raw")
    decision_date = report_data.get("lower_court_decision_date")
    rehearing_denied = report_data.get("lower_court_rehearing_denied_date")

    if not (case_numbers or decision_date or rehearing_denied):
        return None

    # Legacy serialized the list into a comma-joined string.
    docket_number = ", ".join(case_numbers) if case_numbers else None

    return ScotusOCISchema(
        docket_number=docket_number,
        docket_number_raw=_none_if_blank(case_numbers_raw),
        date_judgment=decision_date,
        date_rehearing_denied=rehearing_denied,
    )


# ---------------------------------------------------------------------------
# ScotusDocketMetadata
# ---------------------------------------------------------------------------


def _build_metadata(
    report_data: dict[str, Any],
) -> ScotusDocketMetadataSchema:
    """Build the metadata schema. Always present on a SCOTUS docket
    (singular non-optional child)."""
    qp_url = report_data.get("questions_presented")
    if qp_url and not qp_url.startswith("http"):
        qp_url = urljoin(_SCOTUS_BASE_URL, qp_url)

    return ScotusDocketMetadataSchema(
        capital_case=bool(report_data.get("capital_case")),
        date_discretionary_court_decision=report_data.get(
            "discretionary_court_decision"
        ),
        linked_with=_none_if_blank(report_data.get("links")),
        questions_presented_url=_none_if_blank(qp_url),
    )


# ---------------------------------------------------------------------------
# Docket entries + documents
# ---------------------------------------------------------------------------


def _build_entries(
    report_data: dict[str, Any],
) -> list[ScotusDocketEntrySchema]:
    """Walk the report's ``docket_entries`` and build schemas.

    Replicates the legacy ``enrich_scotus_attachments`` inline:
    attachments get a sequential 1-indexed ``attachment_number`` per
    entry. Unnumbered entries (``document_number is None``) get the
    legacy ``normalize_long_description`` applied to their
    description so the NK pairing on the entry's other fields lines
    up consistently across re-scrapes.
    """
    docket_entries = report_data.get("docket_entries") or []
    sequence_numbers = create_docket_entry_sequence_numbers(
        docket_entries, "date_filed"
    )
    out: list[ScotusDocketEntrySchema] = []
    for entry_dict, sequence_number in zip(
        docket_entries, sequence_numbers, strict=True
    ):
        entry_number = entry_dict.get("document_number")
        description = entry_dict.get("description") or ""
        date_filed = entry_dict.get("date_filed")
        if entry_number is None:
            # Legacy code applies this for unnumbered entries only —
            # numbered entries already have a stable ``entry_number``
            # to key on.
            scratch = {"description": description}
            normalize_long_description(scratch)
            description = scratch["description"]

        attachments = entry_dict.get("attachments") or []
        documents = [
            ScotusDocumentSchema(
                document_number=entry_number,
                attachment_number=idx,
                description=attachment.get("description", "") or "",
                url=attachment["document_url"],
            )
            for idx, attachment in enumerate(attachments, start=1)
        ]

        out.append(
            ScotusDocketEntrySchema(
                entry_number=entry_number,
                description=description,
                date_filed=date_filed,
                sequence_number=sequence_number,
                scotusdocument_set=documents,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Parties, attorneys, roles, attorney-org associations
# ---------------------------------------------------------------------------


def _build_parties_attorneys_orgs(
    parties: list[dict[str, Any]],
) -> tuple[
    list[ScotusPartyTypeSchema],
    list[ScotusRoleSchema],
    list[ScotusAttorneyOrgAssociationSchema],
]:
    """Translate the SCOTUS parties list into the three flat children
    of ``ScotusDocket``.

    Replicates ``normalize_scotus_parties`` inline:
    - Each attorney's contact string is built from title + address +
      city/state/zip + phone + email (newline-joined).
    - LEAD ATTORNEY role for any attorney with
      ``is_counsel_of_record=True``; otherwise no role from the
      scrape (matches the legacy "empty roles list" behavior, which
      becomes ``Role.UNKNOWN`` via the normalizer).
    - Contact-string parsing via ``normalize_attorney_contact`` gives
      us org info (only attached when ``lookup_key`` is present) and
      parsed email/phone/fax.

    Per-name de-duplication: shared ``ScotusPartyRef`` instances
    across roles ensure the framework's id-keyed resolution cache
    picks the same DB row. ``ScotusAttorneyRef`` is intentionally
    *not* cached — each attorney appearance creates a fresh ref so
    the framework's NK-fold picks the latest scalars (via the
    ``ScrapeWins`` annotations on contact fields) when the same
    attorney shows up under multiple parties.
    """
    party_types: list[ScotusPartyTypeSchema] = []
    role_set: list[ScotusRoleSchema] = []
    org_assocs: list[ScotusAttorneyOrgAssociationSchema] = []

    party_refs: dict[str, ScotusPartyRef] = {}

    for party in parties:
        party_name = party.get("name") or ""
        party_type_name = party.get("type") or "Unknown"
        if not party_name:
            continue

        party_ref = party_refs.setdefault(
            party_name, ScotusPartyRef(name=party_name)
        )
        party_types.append(
            ScotusPartyTypeSchema(
                party=party_ref,
                name=party_type_name,
            )
        )

        for atty in party.get("attorneys") or []:
            attorney_name = atty.get("name") or ""
            if not attorney_name:
                continue

            contact = _build_scotus_attorney_contact(atty)
            attorney_org_info, attorney_info = normalize_attorney_contact(
                contact, fallback_name=attorney_name
            )

            # Construct a fresh ScotusAttorneyRef per appearance. When
            # the same attorney name shows up under multiple parties on
            # one docket, the framework NK-folds the resulting distinct
            # instances via the ``ScrapeWinsIfPresent``-annotated scalars
            # on ``ScotusAttorneyRef``.
            #
            # The contact-info gate is a *whole-record* check, not
            # per-field: legacy ``add_attorney`` writes all four contact
            # fields (verbatim, including empty strings the parser
            # didn't extract) iff ``atty["contact"]`` is truthy, and
            # skips them entirely otherwise. We replicate that by
            # passing ``None`` for all four fields when ``contact`` is
            # empty (so ``ScrapeWinsIfPresent`` skips them on fold),
            # and the parsed values verbatim when ``contact`` is
            # truthy (so the fold's last-wins behavior matches the
            # legacy ``a.save()`` last-write-wins behavior, even when
            # individual parsed fields are ``""``).
            if contact:
                contact_raw_v: str | None = contact
                email_v: str | None = attorney_info.get("email", "")
                phone_v: str | None = attorney_info.get("phone", "")
                fax_v: str | None = attorney_info.get("fax", "")
            else:
                contact_raw_v = email_v = phone_v = fax_v = None
            attorney_ref = ScotusAttorneyRef(
                name=attorney_name,
                contact_raw=contact_raw_v,
                email=email_v,
                phone=phone_v,
                fax=fax_v,
            )

            # Mirror the legacy ``add_attorney`` default: when the
            # scrape says the attorney is *not* counsel of record,
            # ``normalize_scotus_parties`` produces an empty roles
            # list, and the legacy default fills in
            # ``role=Role.UNKNOWN`` with no ``role_raw``. When the
            # scrape says counsel of record, the role string
            # "LEAD ATTORNEY" goes through ``normalize_attorney_role``.
            if atty.get("is_counsel_of_record"):
                role_info = normalize_attorney_role("LEAD ATTORNEY")
                role_int = role_info["role"] or 0
                role_raw_value = role_info.get("role_raw", "LEAD ATTORNEY")
                date_action = role_info.get("date_action")
            else:
                role_int = Role.UNKNOWN
                role_raw_value = ""
                date_action = None
            role_set.append(
                ScotusRoleSchema(
                    party=party_ref,
                    attorney=attorney_ref,
                    role=role_int,
                    role_raw=role_raw_value,
                    date_action=date_action,
                )
            )

            if attorney_org_info:
                org_assocs.append(
                    ScotusAttorneyOrgAssociationSchema(
                        attorney=attorney_ref,
                        attorney_organization=ScotusAttorneyOrgRef(
                            lookup_key=attorney_org_info["lookup_key"],
                            name=attorney_org_info.get("name", ""),
                            address1=attorney_org_info.get("address1", ""),
                            address2=attorney_org_info.get("address2", ""),
                            city=attorney_org_info.get("city", ""),
                            state=attorney_org_info.get("state", ""),
                            zip_code=attorney_org_info.get("zip_code", ""),
                        ),
                    )
                )

    return party_types, role_set, org_assocs


def _build_scotus_attorney_contact(atty: dict[str, Any]) -> str:
    """Reproduce ``normalize_scotus_parties``'s contact-string
    composition (title / address / city,state zip / phone / email,
    newline-joined). Returns ``""`` when nothing's present — the
    address parser handles that gracefully."""
    parts: list[str] = []
    if title := atty.get("title"):
        parts.append(title)
    if address := atty.get("address"):
        parts.append(address)

    city_state_zip: list[str] = []
    if city := atty.get("city"):
        city_state_zip.append(city)
    if state := atty.get("state"):
        city_state_zip.append(state)
    if city_state_zip:
        line = ", ".join(city_state_zip)
        if zip_code := atty.get("zip"):
            line += f" {zip_code}"
        parts.append(line)

    if phone := atty.get("phone"):
        parts.append(phone)
    if email := atty.get("email"):
        parts.append(f"Email: {email}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _none_if_blank(value: Any) -> Any:
    """Convention enforcement: empty strings from the source become
    ``None`` so the ``ScrapeWinsIfPresent`` strategy correctly
    preserves DB state. Non-string falsy values (``0``, ``[]``) pass
    through — those usually represent real data when they appear.
    """
    if isinstance(value, str) and not value:
        return None
    return value
