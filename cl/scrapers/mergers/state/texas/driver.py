"""Driver: translate a Juriscraper Texas docket dict into a
``TexasDocket`` scrape instance and run it through the merger
framework.

This is the caller-side adapter that replaces the legacy
``cl.corpus_importer.tasks.merge_texas_docket`` flow. Responsibilities
split between this module and the schema layer (``tames.py``):

- **This module** (the driver): everything that depends on the
  Juriscraper data shape *or* requires DB pre-resolution: court
  lookups, judge lookups, attorney contact parsing, party
  normalization, the CaseTransfer routing decision tree, and
  appellate-disaggregation of legacy ``texapp`` rows.
- **The schema layer** (:mod:`cl.scrapers.mergers.state.texas.tames`):
  the declarative tree the framework consumes — node kinds, NKs,
  per-field strategies, lifecycle hooks.

Public entry point: :func:`merge_texas_docket`. Returns the
framework's ``MergeOutcome`` so callers can iterate
``outcome.follow_ups`` (e.g., the document-download Celery chain).
The ``download_attachments=False`` knob is honored by filtering
download follow-ups out of the returned outcome.

Disaggregation: when a docket is appellate (``CourtType.APPELLATE``),
the driver first looks for a legacy ``texapp`` row with the same
docket number. If found, the row's ``court`` is reassigned to the
correct appellate court (and saved) *before* the merge runs — that
way the framework's NK lookup ``(court, docket_number_core)`` finds
the migrated row. This mirrors the legacy disaggregation in
``merge_texas_docket``.
"""

import logging
from typing import Any

from asgiref.sync import async_to_sync
from django.db import transaction
from juriscraper.state.texas.common import CourtID, CourtType
from juriscraper.state.texas.court_of_appeals import (
    TexasCourtOfAppealsDocket,
)
from juriscraper.state.texas.court_of_criminal_appeals import (
    TexasCourtOfCriminalAppealsDocket,
)
from juriscraper.state.texas.supreme_court import TexasSupremeCourtDocket

from cl.corpus_importer.utils import (
    create_docket_entry_sequence_numbers,
    texas_js_court_id_to_court_id,
    texas_originating_court_to_court_id,
)
from cl.lib.model_helpers import make_texas_docket_number_core
from cl.lib.pacer import (
    normalize_attorney_contact,
    normalize_attorney_role,
)
from cl.people_db.lookup_utils import (
    lookup_judge_by_full_name,
    lookup_judge_by_full_name_and_set_attr,
)
from cl.recap.mergers import find_docket_object
from cl.scrapers.mergers import MergeOutcome, merge_one
from cl.scrapers.mergers.state.texas.tames import (
    TexasAttorneyOrgAssociationSchema,
    TexasAttorneyOrgRef,
    TexasAttorneyRef,
    TexasDestinationTransfer,
    TexasDocket,
    TexasDocketEntrySchema,
    TexasDocumentSchema,
    TexasOCISchema,
    TexasPartyRef,
    TexasPartyTypeSchema,
    TexasRoleSchema,
    TexasTrialCourtDataSchema,
)
from cl.search.models import CaseTransfer, Court, Docket

logger = logging.getLogger(__name__)

TexasDocketData = (
    TexasCourtOfAppealsDocket
    | TexasCourtOfCriminalAppealsDocket
    | TexasSupremeCourtDocket
)

_DOWNLOAD_FOLLOWUP_NAME = "texas-document-download-and-extract"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def merge_texas_docket(
    docket_data: TexasDocketData,
    *,
    using: str = "default",
    download_attachments: bool = True,
) -> MergeOutcome | None:
    """Merge a scraped Texas docket into CourtListener.

    Wraps the entire flow: court resolution, ``texapp`` disaggregation,
    schema construction with all pre-resolved Django instances, and
    the framework's 4-phase merge. Returns the resulting
    ``MergeOutcome`` (or ``None`` if pre-resolution failed before the
    merge could run, mirroring legacy "failed Docket" cases).

    :param docket_data: Parsed Juriscraper docket dict.
    :param using: Django database alias to write to.
    :param download_attachments: When False, document-download
        follow-ups are stripped from the returned outcome so the
        caller doesn't kick them off.
    """
    docket_number = docket_data["docket_number"]
    logger.info("Merging Texas docket %s", docket_number)

    if docket_data["court_type"] == CourtType.UNKNOWN.value:
        logger.error("Texas docket %s has unknown court type", docket_number)
        return None

    court_id = texas_js_court_id_to_court_id(docket_data["court_id"])
    if court_id is None:
        logger.error(
            "Texas docket %s has unknown court id %s",
            docket_number,
            docket_data["court_id"],
        )
        return None
    court = Court.objects.using(using).get(pk=court_id)

    with transaction.atomic(using=using):
        _disaggregate_texapp_if_needed(
            docket_data, court=court, using=using
        )
        scrape = _build_texas_docket_scrape(docket_data, court=court)
        outcome = merge_one(scrape, using=using)

    if not download_attachments:
        outcome = MergeOutcome(
            root=outcome.root,
            creates=outcome.creates,
            updates=outcome.updates,
            deletes=outcome.deletes,
            follow_ups=[
                fu
                for fu in outcome.follow_ups
                if getattr(fu, "name", None) != _DOWNLOAD_FOLLOWUP_NAME
            ],
        )
    return outcome


# ---------------------------------------------------------------------------
# Disaggregation: migrate legacy ``texapp`` rows to proper appellate court
# ---------------------------------------------------------------------------


def _disaggregate_texapp_if_needed(
    docket_data: TexasDocketData,
    *,
    court: Court,
    using: str,
) -> None:
    """For appellate dockets, check for a legacy ``texapp`` row with
    the same docket number and migrate its ``court`` FK to the proper
    appellate court before the merge runs. If no ``texapp`` row
    exists, this is a no-op — the framework's NK lookup will find or
    create the row under the correct court.
    """
    if docket_data["court_type"] != CourtType.APPELLATE.value:
        return
    logger.info(
        "Docket is appellate. Checking if disaggregation is necessary..."
    )
    texapp_docket = async_to_sync(find_docket_object)(
        court_id="texapp",
        pacer_case_id=None,
        docket_number=docket_data["docket_number"],
        federal_defendant_number=None,
        federal_dn_judge_initials_assigned=None,
        federal_dn_judge_initials_referred=None,
        docket_source=Docket.SCRAPER,
        allow_create=False,
        using=using,
    )
    if texapp_docket is None:
        return
    logger.info(
        "Disaggregating Texas appellate docket %s", docket_data["docket_number"]
    )
    texapp_docket.court = court
    texapp_docket.save(using=using)


# ---------------------------------------------------------------------------
# Top-level schema construction
# ---------------------------------------------------------------------------


def _build_texas_docket_scrape(
    docket_data: TexasDocketData, *, court: Court
) -> TexasDocket:
    """Construct the full ``TexasDocket`` scrape tree from
    ``docket_data``. All Django-side pre-resolution (court lookups,
    judge lookups, etc.) happens here."""
    docket_number = docket_data["docket_number"]

    appeal_from, appeal_from_str = _resolve_appeal_from(docket_data)
    oci = _build_oci(docket_data)
    tcd = _build_trial_court_data(docket_data)
    party_types, role_set, attorney_org_associations = (
        _build_parties_attorneys_orgs(docket_data["parties"])
    )
    entries = _build_entries(docket_data)
    destination_transfers = _build_case_transfers(docket_data, court=court)

    return TexasDocket(
        court=court,
        docket_number=docket_number,
        docket_number_core=make_texas_docket_number_core(docket_number),
        docket_number_raw=docket_number,
        date_filed=docket_data["date_filed"],
        cause=docket_data["case_type"],
        case_name=docket_data["case_name"],
        case_name_full=docket_data["case_name_full"],
        appeal_from=appeal_from,
        appeal_from_str=appeal_from_str,
        source=Docket.SCRAPER,
        originating_court_information=oci,
        trialcourtdata=tcd,
        texasdocketentry_set=entries,
        party_types=party_types,
        role_set=role_set,
        attorneyorganizationassociation_set=attorney_org_associations,
        case_transfer_destination_docket=destination_transfers,
    )


# ---------------------------------------------------------------------------
# appeal_from
# ---------------------------------------------------------------------------


def _resolve_appeal_from(
    docket_data: TexasDocketData,
) -> tuple[Court | None, str]:
    """Return ``(appeal_from, appeal_from_str)`` for the docket.

    Mirrors the legacy branching: appellate dockets use
    ``appeals_court`` (with court_id mapping), trial-origin dockets
    use ``originating_court``. The string fallback is the
    Juriscraper-provided name when the Court lookup misses.
    """
    if _has_appellate_info(docket_data):
        lower_court_data = docket_data["appeals_court"]
        lower_court_id = texas_js_court_id_to_court_id(
            lower_court_data["court_id"]
        )
        lower_court_name = lower_court_data["district"]
    else:
        lower_court_data = docket_data["originating_court"]
        lower_court_id = texas_originating_court_to_court_id(
            lower_court_data
        )
        lower_court_name = lower_court_data.get("name", "")

    if not lower_court_id:
        return None, lower_court_name
    try:
        court = Court.objects.get(pk=lower_court_id)
    except Court.DoesNotExist:
        logger.error(
            "Could not find lower court with ID %s to set appeal_from",
            lower_court_id,
        )
        return None, lower_court_name
    return court, court.full_name


# ---------------------------------------------------------------------------
# OriginatingCourtInformation (OCI)
# ---------------------------------------------------------------------------


def _build_oci(docket_data: TexasDocketData) -> TexasOCISchema | None:
    """Build the ``TexasOCISchema`` for this docket, or ``None`` when
    there's no usable originating-court information.

    Branches identically to legacy ``merge_texas_docket_originating_court``:
    appellate dockets read from ``appeals_court`` (and require a
    non-empty case_number list), trial-origin dockets read from
    ``originating_court``. Judge lookup runs via
    ``lookup_judge_by_full_name_and_set_attr`` against the resolved
    court — when the lookup misses, ``ScrapeWinsIfPresent`` on the
    schema field preserves any existing DB value.
    """
    if _has_appellate_info(docket_data):
        ocd = docket_data["appeals_court"]
        if not ocd["case_number"]:
            logger.warning(
                "Skipping OCI for Texas docket %s due to missing originating "
                "court docket number.",
                docket_data["docket_number"],
            )
            return None
        oc_dn = sorted(ocd["case_number"])[0]
        oc_reporter = ""
        oc_judge_name = ocd["justice"]
        oc_id = texas_js_court_id_to_court_id(ocd["court_id"])
    elif (
        docket_data["originating_court"]["court_type"]
        != CourtType.UNKNOWN.value
    ):
        ocd = docket_data["originating_court"]
        oc_dn = ocd["case"]
        oc_reporter = ocd["reporter"]
        oc_judge_name = ocd["judge"]
        oc_id = texas_originating_court_to_court_id(ocd)
    else:
        logger.warning(
            "Skipping OCI for Texas docket %s due to unknown originating "
            "court type.",
            docket_data["docket_number"],
        )
        return None

    # Judge lookup: the legacy helper sets ``oci.assigned_to`` in place
    # via a shim object; we just want the resolved Person.
    assigned_to = None
    if oc_id and oc_judge_name:
        shim: Any = type("Shim", (), {"assigned_to": None})()
        async_to_sync(lookup_judge_by_full_name_and_set_attr)(
            item=shim,
            target_field="assigned_to",
            full_name=oc_judge_name,
            court_id=oc_id,
            event_date=None,
            require_living_judge=False,
        )
        assigned_to = shim.assigned_to

    return TexasOCISchema(
        docket_number=oc_dn,
        docket_number_raw=oc_dn,
        court_reporter=oc_reporter,
        assigned_to_str=oc_judge_name,
        assigned_to=assigned_to,
    )


# ---------------------------------------------------------------------------
# TrialCourtData (SC + CCA only)
# ---------------------------------------------------------------------------


def _build_trial_court_data(
    docket_data: TexasDocketData,
) -> TexasTrialCourtDataSchema | None:
    """Build a ``TexasTrialCourtDataSchema`` for SC and CCA dockets
    when the originating court isn't appellate. Returns ``None``
    otherwise — the framework treats ``None`` on a ``T | None`` field
    as "no row in this collection."
    """
    court_id_str = docket_data["court_id"]
    is_sc_or_cca = court_id_str in (
        CourtID.SUPREME_COURT.value,
        CourtID.COURT_OF_CRIMINAL_APPEALS.value,
    )
    if not is_sc_or_cca:
        return None

    originating = docket_data["originating_court"]
    if originating["court_type"] == CourtType.APPELLATE.value:
        # Same short-circuit as legacy: TCD is only meaningful when
        # the trial court is below an SC/CCA case.
        return None

    court_id = texas_originating_court_to_court_id(originating)
    court = None
    court_name = originating["name"]
    judge = None
    if court_id:
        try:
            court = Court.objects.get(pk=court_id)
        except Court.DoesNotExist:
            logger.error("Court with ID %s not found.", court_id)
            court = None
        else:
            court_name = court.full_name
        if originating["judge"]:
            judge = async_to_sync(lookup_judge_by_full_name)(
                name=originating["judge"],
                court_id=court_id,
                event_date=None,
                require_living_judge=False,
            )

    return TexasTrialCourtDataSchema(
        docket_number_trial=originating["case"],
        docket_number_raw_trial=originating["case"],
        judge_str=originating["judge"],
        judge=judge,
        reporter=originating["reporter"],
        court_name=court_name,
        court=court,
        punishment=originating["punishment"],
        county=originating["county"],
    )


# ---------------------------------------------------------------------------
# Parties, attorneys, roles, attorney-org associations
# ---------------------------------------------------------------------------


def _build_parties_attorneys_orgs(
    parties: list[dict[str, Any]],
) -> tuple[
    list[TexasPartyTypeSchema],
    list[TexasRoleSchema],
    list[TexasAttorneyOrgAssociationSchema],
]:
    """Translate the Juriscraper ``parties`` list into the three flat
    children of ``TexasDocket``: ``party_types``, ``role_set``, and
    ``attorneyorganizationassociation_set``.

    The legacy ``normalize_texas_parties`` shape is replicated inline:
    each party has a list of attorneys keyed by ``name`` / ``contact``,
    with the first attorney getting ``LEAD_ATTORNEY`` role and the rest
    ``UNKNOWN``. For each attorney we run
    ``normalize_attorney_contact`` to extract email/phone/fax plus an
    optional org with ``lookup_key`` — only when org parsing yielded
    something usable do we construct an ``AttorneyOrgAssociationSchema``.

    Shared ExternalNodeRef instances by attorney/party name keep the
    framework's id-keyed resolution cache happy and ensure a single
    Party / Attorney row gets reused across multiple PartyTypes /
    Roles within this docket.
    """
    party_types: list[TexasPartyTypeSchema] = []
    role_set: list[TexasRoleSchema] = []
    org_assocs: list[TexasAttorneyOrgAssociationSchema] = []

    party_refs: dict[str, TexasPartyRef] = {}
    attorney_refs: dict[str, TexasAttorneyRef] = {}

    for party in parties:
        party_name = party["name"]
        party_type_name = party["type"]
        party_ref = party_refs.setdefault(
            party_name, TexasPartyRef(name=party_name)
        )

        party_types.append(
            TexasPartyTypeSchema(
                party=party_ref,
                name=party_type_name,
            )
        )

        representatives = [
            rep for rep in party.get("representatives", []) if len(rep) > 0
        ]
        for i, attorney_name in enumerate(representatives):
            role_raw = "LEAD_ATTORNEY" if i == 0 else "UNKNOWN"
            role_info = normalize_attorney_role(role_raw)
            attorney_org_info, attorney_info = normalize_attorney_contact(
                attorney_name, fallback_name=attorney_name
            )

            attorney_ref = attorney_refs.get(attorney_name)
            if attorney_ref is None:
                attorney_ref = TexasAttorneyRef(
                    name=attorney_name,
                    contact_raw=attorney_name,
                    email=attorney_info.get("email", ""),
                    phone=attorney_info.get("phone", ""),
                    fax=attorney_info.get("fax", ""),
                )
                attorney_refs[attorney_name] = attorney_ref

            role_set.append(
                TexasRoleSchema(
                    party=party_ref,
                    attorney=attorney_ref,
                    # ``normalize_attorney_role`` returns ``None`` for
                    # roles it doesn't recognize (notably Texas's
                    # ``"LEAD_ATTORNEY"`` with an underscore, since
                    # the legacy matcher looks for "lead attorney"
                    # with a space). Pass it through unchanged so the
                    # new driver matches legacy DB state exactly.
                    role=role_info["role"],
                    role_raw=role_info.get("role_raw", role_raw),
                    date_action=role_info.get("date_action"),
                )
            )

            if attorney_org_info:
                org_assocs.append(
                    TexasAttorneyOrgAssociationSchema(
                        attorney=attorney_ref,
                        attorney_organization=TexasAttorneyOrgRef(
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


# ---------------------------------------------------------------------------
# Docket entries + documents
# ---------------------------------------------------------------------------


def _build_entries(
    docket_data: TexasDocketData,
) -> list[TexasDocketEntrySchema]:
    """Walk ``case_events`` zipped with sequence numbers and pair with
    ``appellate_briefs`` using the legacy zip-iter pattern: a brief
    matches if its (date, type, attachments) match the next case event.

    Each entry carries its attachments as a list of
    ``TexasDocumentSchema`` instances; the schema's ``on_update`` hook
    emits the download Celery chain on insert or media-version change.
    """
    case_events = docket_data["case_events"]
    appellate_briefs = docket_data["appellate_briefs"]

    brief_iter = iter(appellate_briefs)
    next_brief = next(brief_iter, None)

    out: list[TexasDocketEntrySchema] = []
    sequence_numbers = create_docket_entry_sequence_numbers(case_events)
    for case_event, sequence_number in zip(case_events, sequence_numbers):
        appellate_brief: dict[str, Any] | None = None
        if (
            next_brief is not None
            and case_event["date"] == next_brief["date"]
            and case_event["type"] == next_brief["type"]
            and case_event["attachments"] == next_brief["attachments"]
        ):
            appellate_brief = next_brief
            next_brief = next(brief_iter, None)

        documents = [
            TexasDocumentSchema(
                media_id=attachment["media_id"],
                media_version_id=attachment["media_version_id"],
                description=attachment.get("description", ""),
                url=attachment["document_url"],
            )
            for attachment in case_event["attachments"]
        ]

        out.append(
            TexasDocketEntrySchema(
                date_filed=case_event["date"],
                entry_type=case_event["type"],
                appellate_brief=appellate_brief is not None,
                sequence_number=sequence_number,
                description=(
                    appellate_brief["description"]
                    if appellate_brief
                    else ""
                ),
                disposition=case_event.get("disposition", ""),
                remarks=case_event.get("remarks", ""),
                texasdocument_set=documents,
            )
        )
    return out


# ---------------------------------------------------------------------------
# CaseTransfer routing (the big branching block)
# ---------------------------------------------------------------------------


def _build_case_transfers(
    docket_data: TexasDocketData, *, court: Court
) -> list[TexasDestinationTransfer]:
    """Decide which ``CaseTransfer`` rows to emit for this docket and
    return them as ``TexasDestinationTransfer`` instances (this docket
    is always the destination side of every Texas transfer).

    Ported from legacy ``merge_texas_case_transfers``. The match
    statement on ``court_id`` decides the APPEAL transfer's origin
    court + docket numbers; for COA dockets there may also be an
    incoming WORKLOAD / JURISDICTION transfer captured in
    ``transfer_from``. Returns an empty list when the routing decision
    couldn't determine a usable origin court (legacy "failed
    CaseTransfer" cases — they log and continue).

    The framework's ``BridgeNode`` machinery handles the rest: each
    returned schema is globally looked up by 6-tuple NK, inserted if
    missing with ``destination_docket`` auto-injected from the parent
    field name, or updated to fill in the previously-NULL
    ``destination_docket`` if a matching row exists.
    """
    docket_number = docket_data["docket_number"]
    originating_court = docket_data["originating_court"]
    oc_dn: str = originating_court["case"]
    appeals_court = docket_data.get("appeals_court", {})
    ac_id = appeals_court.get("court_id", "")
    ac_dns: list[str] = appeals_court.get("case_number", [])
    trial_court_id = texas_originating_court_to_court_id(originating_court)

    appeal_origin_court_id: str | None = None
    appeal_origin_dns: list[str] = []
    extras: list[TexasDestinationTransfer] = []

    match docket_data["court_id"]:
        case CourtID.COURT_OF_CRIMINAL_APPEALS.value if (
            ac_id == CourtID.UNKNOWN.value
        ):
            logger.info(
                "Docket %s in the CCA is a death penalty appeal",
                docket_number,
            )
            if not trial_court_id:
                logger.error(
                    "Unable to determine trial court ID for Texas docket %s "
                    "to create death penalty appeal CaseTransfer",
                    docket_number,
                )
                return []
            appeal_origin_dns = [oc_dn]
            appeal_origin_court_id = trial_court_id

        case CourtID.COURT_OF_CRIMINAL_APPEALS.value:
            logger.info(
                "Docket %s is a non-death penalty CCA docket", docket_number
            )
            appeal_origin_dns = ac_dns
            appeal_origin_court_id = texas_js_court_id_to_court_id(ac_id)

        case CourtID.SUPREME_COURT.value if (
            ac_id == CourtID.UNKNOWN.value
        ):
            if originating_court["court_type"] == CourtType.UNKNOWN.value:
                logger.warning(
                    "Found Texas SC docket with no originating or appellate "
                    "information (docket number %s).",
                    docket_number,
                )
                return []
            logger.warning(
                "Found Texas SC docket with originating information but no "
                "appellate information (docket number %s). Falling back to "
                "using trial court to create appeal type transfer.",
                docket_number,
            )
            appeal_origin_dns = [oc_dn]
            appeal_origin_court_id = trial_court_id

        case CourtID.SUPREME_COURT.value:
            logger.info("Docket %s is a SC docket", docket_number)
            appeal_origin_court_id = texas_js_court_id_to_court_id(ac_id)
            appeal_origin_dns = ac_dns

        case _ if docket_data["court_type"] == CourtType.APPELLATE.value:
            logger.info(
                "Docket %s is an appellate docket", docket_number
            )
            appeal_origin_court_id = trial_court_id
            appeal_origin_dns = [oc_dn]

            transfer_from = docket_data.get("transfer_from")
            if transfer_from:
                extras = _build_coa_workload_transfers(
                    docket_data,
                    court=court,
                    transfer_from=transfer_from,
                )

        case _:
            logger.error(
                "Unrecognized Texas court ID %s and type %s while creating "
                "CaseTransfer",
                docket_data["court_id"],
                docket_data["court_type"],
            )
            return []

    appeals: list[TexasDestinationTransfer] = []
    if appeal_origin_court_id:
        try:
            appeal_origin_court = Court.objects.get(pk=appeal_origin_court_id)
        except Court.DoesNotExist:
            logger.error(
                "Court with ID %s not found while populating "
                "CaseTransfer.origin_court with appeal type.",
                appeal_origin_court_id,
            )
        else:
            for origin_dn in appeal_origin_dns:
                appeals.append(
                    TexasDestinationTransfer(
                        origin_court=appeal_origin_court,
                        origin_docket_number=origin_dn,
                        destination_court=court,
                        destination_docket_number=docket_number,
                        transfer_date=docket_data["date_filed"],
                        transfer_type=CaseTransfer.APPEAL,
                    )
                )
    return [*appeals, *extras]


def _build_coa_workload_transfers(
    docket_data: TexasDocketData,
    *,
    court: Court,
    transfer_from: dict[str, Any],
) -> list[TexasDestinationTransfer]:
    """A COA docket can record an incoming workload / jurisdiction
    transfer in ``transfer_from``. The transfer_type is
    ``JURISDICTION`` only for the Fifteenth Court of Appeals (per
    Texas Gov. Code 73.001), ``WORKLOAD`` otherwise.
    """
    docket_number = docket_data["docket_number"]
    logger.info(
        "Appellate docket %s has an incoming transfer", docket_number
    )

    transfer_date = transfer_from["date"]
    if not transfer_date:
        logger.warning(
            "Missing transfer date for transfer of docket %s. Defaulting "
            "to filing date.",
            docket_number,
        )
        transfer_date = docket_data["date_filed"]

    origin_court_id = texas_js_court_id_to_court_id(
        transfer_from["court_id"]
    )
    if not origin_court_id:
        logger.warning(
            "Could not determine origin court for workload transfer of "
            "docket %s. Skipping workload transfer.",
            docket_number,
        )
        return []
    try:
        origin_court = Court.objects.get(pk=origin_court_id)
    except Court.DoesNotExist:
        logger.error(
            "Court with ID %s not found while populating "
            "CaseTransfer.origin_court.",
            origin_court_id,
        )
        return []

    transfer_type = (
        CaseTransfer.JURISDICTION
        if docket_data["court_id"]
        == CourtID.FIFTEENTH_COURT_OF_APPEALS.value
        else CaseTransfer.WORKLOAD
    )
    return [
        TexasDestinationTransfer(
            origin_court=origin_court,
            origin_docket_number=transfer_from["origin_docket"],
            destination_court=court,
            destination_docket_number=docket_number,
            transfer_date=transfer_date,
            transfer_type=transfer_type,
        )
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_appellate_info(docket_data: TexasDocketData) -> bool:
    """Direct port of legacy ``texas_docket_has_appellate_info``: true
    when this docket is *not* itself an appellate-court docket *and*
    the ``appeals_court`` block carries a non-UNKNOWN court_id."""
    if docket_data["court_type"] == CourtType.APPELLATE.value:
        return False
    appeals_court = docket_data.get("appeals_court")
    if not appeals_court:
        return False
    return appeals_court.get("court_id") != CourtID.UNKNOWN.value
