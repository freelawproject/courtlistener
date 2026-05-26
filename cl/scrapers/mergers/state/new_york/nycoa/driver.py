"""Driver: load a kent NYCoA Court-PASS run and merge each docket
into CourtListener.

Subclasses :class:`KentMerger` with the NYCoA-specific bits:

- ``aggregate_cls`` → :class:`NYCoADocket`.
- ``sql_path`` → ``load.sql`` (CTE-stacked one-row-per-docket query).
- ``normalize(row)`` → collapses Court-PASS whitespace in case names,
  restructures the flat attorneys array into party_types / role_set /
  attorneyorganizationassociation_set lists, and merges the SQL's two
  entry lists (FILINGS-derived + file-only) into the single Pydantic
  ``nycoadocketentry_set`` field.

The ``court`` and per-attorney contact pre-resolution happens in
``normalize`` so the framework only sees ready-to-validate dicts.
"""

import logging
import re
from typing import Any

from cl.lib.pacer import normalize_attorney_contact
from cl.scrapers.mergers import KentMerger
from cl.scrapers.mergers.state.new_york.nycoa.nycoa import (
    NYCoAAttorneyOrgAssociationSchema,
    NYCoAAttorneyOrgRef,
    NYCoAAttorneyRef,
    NYCoADocket,
    NYCoAPartyRef,
    NYCoAPartyTypeSchema,
    NYCoARoleSchema,
)
from cl.search.models import Court

logger = logging.getLogger(__name__)


# Court-PASS captions have embedded line breaks and runs of whitespace
# from the source HTML; collapse them so case_name reads naturally.
_WHITESPACE_RE = re.compile(r"\s+")


def _collapse_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()


class NYCoAMerger(KentMerger[NYCoADocket]):
    """KentMerger driver for the NYCoA Court-PASS scraper.

    Subclasses set ``aggregate_cls`` and ``sql_path``; the only
    NYCoA-specific work is in ``normalize`` (Court-PASS data shape →
    framework-shape) and the cached Court lookup.
    """

    aggregate_cls = NYCoADocket
    sql_path = "load.sql"

    def __init__(self, kent_db_path, *, using: str = "default") -> None:
        super().__init__(kent_db_path, using=using)
        # NYCoA is single-court; resolve once and reuse across rows.
        self._court: Court | None = None

    @property
    def court(self) -> Court:
        if self._court is None:
            self._court = Court.objects.using(self.using).get(pk="ny")
        return self._court

    def normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        """Transform the SQL row into the shape the schemas expect.

        Three things happen here:

        1. ``court`` is hydrated to a real ``Court`` instance — the
           SQL emits the string ``"ny"``, but the schema's
           ``PreResolvedRef[Court]`` wants the model.
        2. Case names are whitespace-collapsed (Court-PASS captions
           carry source HTML's newlines and runs of spaces).
        3. The flat ``attorneys`` array is restructured into the three
           framework-shape lists: ``party_types``, ``role_set``, and
           ``attorneyorganizationassociation_set``. Normalization of
           contact strings (address parsing, lookup_key derivation)
           runs here too via :func:`normalize_attorney_contact`.
        4. ``filings_entries`` + ``file_entries`` are merged into a
           single ``nycoadocketentry_set`` list (the framework treats
           them uniformly; only their sequence_number prefix
           distinguishes them).
        """
        case_name = _collapse_whitespace(row.get("case_name"))
        case_name_short = _collapse_whitespace(row.get("case_name_short"))
        case_name_full = _collapse_whitespace(row.get("case_name_full"))

        party_types, role_set, org_assocs = self._restructure_attorneys(
            row.get("attorneys") or []
        )

        entries = list(row.get("filings_entries") or []) + list(
            row.get("file_entries") or []
        )

        return {
            "court": self.court,
            "docket_number": row["docket_number"],
            "docket_number_raw": row.get("docket_number_raw")
            or row["docket_number"],
            "case_name": case_name or None,
            "case_name_short": case_name_short or None,
            "case_name_full": case_name_full or None,
            "date_argued": row.get("date_argued"),
            "date_filed": row.get("date_filed"),
            "source": 0,  # Custom strategy ORs in SCRAPER on update.
            "nycoadocketentry_set": entries,
            "party_types": party_types,
            "role_set": role_set,
            "attorneyorganizationassociation_set": org_assocs,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _restructure_attorneys(
        self, attorneys: list[dict[str, Any]]
    ) -> tuple[
        list[NYCoAPartyTypeSchema],
        list[NYCoARoleSchema],
        list[NYCoAAttorneyOrgAssociationSchema],
    ]:
        """Flatten the attorneys array into the three child collections
        ``NYCoADocket`` declares. The framework's resolution cache is
        keyed by Python ``id()`` of each ``ExternalNodeRef`` instance, so we
        build real ``NYCoAPartyRef`` / ``NYCoAAttorneyRef`` /
        ``NYCoAAttorneyOrgRef`` instances here (not dicts) and reuse
        them across overlapping party / role / org-association rows.
        Reusing the same instance across rows is what causes the
        framework to resolve them to a single DB row per name.
        """
        party_types: list[NYCoAPartyTypeSchema] = []
        role_set: list[NYCoARoleSchema] = []
        org_assocs: list[NYCoAAttorneyOrgAssociationSchema] = []

        party_refs: dict[str, NYCoAPartyRef] = {}
        attorney_refs: dict[str, NYCoAAttorneyRef] = {}
        org_refs: dict[str, NYCoAAttorneyOrgRef] = {}

        seen_party_type_keys: set[tuple[str, str]] = set()
        seen_role_keys: set[tuple[str, str, str]] = set()
        seen_org_assoc_keys: set[tuple[str, str]] = set()

        for atty in attorneys:
            party_name = (atty.get("party_name") or "").strip()
            party_role = (atty.get("party_role") or "").strip()
            attorney_name = (atty.get("attorney_name") or "").strip()
            if not party_name:
                continue

            party_ref = party_refs.get(party_name)
            if party_ref is None:
                party_ref = NYCoAPartyRef(name=party_name)
                party_refs[party_name] = party_ref

            pt_key = (party_name, party_role)
            if pt_key not in seen_party_type_keys:
                seen_party_type_keys.add(pt_key)
                party_types.append(
                    NYCoAPartyTypeSchema(
                        party=party_ref, name=party_role or "Unknown"
                    )
                )

            if not attorney_name:
                continue

            contact = _build_attorney_contact(atty)
            org_info, parsed = normalize_attorney_contact(
                contact, fallback_name=attorney_name
            )

            attorney_ref = attorney_refs.get(attorney_name)
            if attorney_ref is None:
                attorney_ref = NYCoAAttorneyRef(
                    name=attorney_name,
                    contact_raw=contact,
                    phone=parsed.get("phone", "")
                    or atty.get("phone", "")
                    or "",
                )
                attorney_refs[attorney_name] = attorney_ref

            role_key = (party_name, attorney_name, party_role)
            if role_key not in seen_role_keys:
                seen_role_keys.add(role_key)
                role_set.append(
                    NYCoARoleSchema(
                        party=party_ref,
                        attorney=attorney_ref,
                        role=0,
                        role_raw=party_role,
                        date_action=None,
                    )
                )

            if org_info and (lookup_key := org_info.get("lookup_key")):
                org_ref = org_refs.get(lookup_key)
                if org_ref is None:
                    org_ref = NYCoAAttorneyOrgRef(
                        lookup_key=lookup_key,
                        name=org_info.get("name", ""),
                        address1=org_info.get("address1", ""),
                        address2=org_info.get("address2", ""),
                        city=org_info.get("city", ""),
                        state=org_info.get("state", ""),
                        zip_code=org_info.get("zip_code", ""),
                    )
                    org_refs[lookup_key] = org_ref
                aoa_key = (attorney_name, lookup_key)
                if aoa_key not in seen_org_assoc_keys:
                    seen_org_assoc_keys.add(aoa_key)
                    org_assocs.append(
                        NYCoAAttorneyOrgAssociationSchema(
                            attorney=attorney_ref,
                            attorney_organization=org_ref,
                        )
                    )

        return party_types, role_set, org_assocs


def _build_attorney_contact(atty: dict[str, Any]) -> str:
    """Compose a multi-line contact string suitable for the
    ``normalize_attorney_contact`` parser. Court-PASS gives firm /
    address / phone as separate fields; newline-joining mirrors the
    SCOTUS approach.
    """
    parts: list[str] = []
    if firm := atty.get("firm"):
        parts.append(firm)
    if address := atty.get("address"):
        parts.append(address)
    if phone := atty.get("phone"):
        parts.append(phone)
    return "\n".join(parts)
