# Code for merging PACER content into the DB
import logging
import re
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Prefetch, Q, QuerySet
from django.utils.timezone import now
from juriscraper.lib.string_utils import CaseNameTweaker
from juriscraper.pacer import AppellateAttachmentPage, AttachmentPage

from cl.corpus_importer.utils import mark_ia_upload_needed
from cl.lib.decorators import retry
from cl.lib.filesizes import convert_size_to_bytes
from cl.lib.model_helpers import clean_docket_number, make_docket_number_core
from cl.lib.pacer import (
    get_blocked_status,
    map_cl_to_pacer_id,
    map_pacer_to_cl_id,
    normalize_attorney_contact,
    normalize_attorney_role,
)
from cl.lib.privacy_tools import anonymize
from cl.lib.stop_words import STOP_WORDS
from cl.lib.timezone_helpers import localize_date_and_time
from cl.lib.utils import previous_and_next, remove_duplicate_dicts
from cl.people_db.lookup_utils import lookup_judge_by_full_name_and_set_attr
from cl.people_db.models import (
    Attorney,
    AttorneyOrganization,
    AttorneyOrganizationAssociation,
    CriminalComplaint,
    CriminalCount,
    Party,
    PartyType,
    Role,
)
from cl.recap.models import (
    PROCESSING_STATUS,
    UPLOAD_TYPE,
    PacerHtmlFiles,
    ProcessingQueue,
)
from cl.search.models import (
    BankruptcyInformation,
    Claim,
    ClaimHistory,
    Court,
    Docket,
    DocketEntry,
    OriginatingCourtInformation,
    RECAPDocument,
    Tag,
)
from cl.search.tasks import add_items_to_solr

logger = logging.getLogger(__name__)

cnt = CaseNameTweaker()


def confirm_docket_number_core_lookup_match(
    docket: Docket,
    docket_number: str,
) -> Docket | None:
    """Confirm if the docket_number_core lookup match returns the right docket
    by confirming the docket_number also matches.

    :param docket: The docket matched by the lookup
    :param docket_number: The incoming docket_number to lookup.
    :return: The docket object if both dockets matched or otherwise None.
    """
    existing_docket_number = clean_docket_number(docket.docket_number)
    incoming_docket_number = clean_docket_number(docket_number)
    if existing_docket_number != incoming_docket_number:
        return None
    return docket


def find_docket_object(
    court_id: str,
    pacer_case_id: str | None,
    docket_number: str,
    using: str = "default",
) -> Docket:
    """Attempt to find the docket based on the parsed docket data. If cannot be
    found, create a new docket. If multiple are found, return the oldest.

    :param court_id: The CourtListener court_id to lookup
    :param pacer_case_id: The PACER case ID for the docket
    :param docket_number: The docket number to lookup.
    :param using: The database to use for the lookup queries.
    :return The docket found or created.
    """
    # Attempt several lookups of decreasing specificity. Note that
    # pacer_case_id is required for Docket and Docket History uploads.
    d = None
    docket_number_core = make_docket_number_core(docket_number)
    lookups = []
    if pacer_case_id:
        # Appellate RSS feeds don't contain a pacer_case_id, avoid lookups by
        # blank pacer_case_id values.
        lookups = [
            {
                "pacer_case_id": pacer_case_id,
                "docket_number_core": docket_number_core,
            },
            {"pacer_case_id": pacer_case_id},
        ]
    if docket_number_core:
        # Sometimes we don't know how to make core docket numbers. If that's
        # the case, we will have a blank value for the field. We must not do
        # lookups by blank values. See: freelawproject/courtlistener#1531
        lookups.extend(
            [
                {
                    "pacer_case_id": None,
                    "docket_number_core": docket_number_core,
                },
                {"docket_number_core": docket_number_core},
            ]
        )
    else:
        # Finally, as a last resort, we can try the docket number. It might not
        # match b/c of punctuation or whatever, but we can try. Avoid lookups
        # by blank docket_number values.
        if docket_number:
            lookups.append(
                {"pacer_case_id": None, "docket_number": docket_number},
            )

    for kwargs in lookups:
        ds = Docket.objects.filter(court_id=court_id, **kwargs).using(using)
        count = ds.count()
        if count == 0:
            continue  # Try a looser lookup.
        if count == 1:
            d = ds[0]
            if kwargs.get("pacer_case_id") is None and kwargs.get(
                "docket_number_core"
            ):
                d = confirm_docket_number_core_lookup_match(d, docket_number)
            if d:
                break  # Nailed it!
        elif count > 1:
            # Choose the oldest one and live with it.
            d = ds.earliest("date_created")
            if kwargs.get("pacer_case_id") is None and kwargs.get(
                "docket_number_core"
            ):
                d = confirm_docket_number_core_lookup_match(d, docket_number)
            if d:
                break
    if d is None:
        # Couldn't find a docket. Return a new one.
        return Docket(
            source=Docket.RECAP,
            pacer_case_id=pacer_case_id,
            court_id=court_id,
        )

    if using != "default":
        # Get the item from the default DB
        d = Docket.objects.get(pk=d.pk)

    return d


def add_attorney(atty, p, d):
    """Add/update an attorney.

    Given an attorney node, and a party and a docket object, add the attorney
    to the database or link the attorney to the new docket. Also add/update the
    attorney organization, and the attorney's role in the case.

    :param atty: A dict representing an attorney, as provided by Juriscraper.
    :param p: A Party object
    :param d: A Docket object
    :return: None if there's an error, or an Attorney ID if not.
    """
    atty_org_info, atty_info = normalize_attorney_contact(
        atty["contact"], fallback_name=atty["name"]
    )

    # Try lookup by atty name in the docket.
    attys = Attorney.objects.filter(
        name=atty["name"], roles__docket=d
    ).distinct()
    count = attys.count()
    if count == 0:
        # Couldn't find the attorney. Make one.
        a = Attorney.objects.create(
            name=atty["name"], contact_raw=atty["contact"]
        )
    elif count == 1:
        # Nailed it.
        a = attys[0]
    elif count >= 2:
        # Too many found, choose the most recent attorney.
        logger.info(
            f"Got too many results for atty: '{atty}'. Picking earliest."
        )
        a = attys.earliest("date_created")

    # Associate the attorney with an org and update their contact info.
    if atty["contact"]:
        if atty_org_info:
            try:
                org = AttorneyOrganization.objects.get(
                    lookup_key=atty_org_info["lookup_key"],
                )
            except AttorneyOrganization.DoesNotExist:
                try:
                    org = AttorneyOrganization.objects.create(**atty_org_info)
                except IntegrityError:
                    # Race condition. Item was created after get. Try again.
                    org = AttorneyOrganization.objects.get(
                        lookup_key=atty_org_info["lookup_key"],
                    )

            # Add the attorney to the organization
            AttorneyOrganizationAssociation.objects.get_or_create(
                attorney=a, attorney_organization=org, docket=d
            )

        if atty_info:
            a.contact_raw = atty["contact"]
            a.email = atty_info["email"]
            a.phone = atty_info["phone"]
            a.fax = atty_info["fax"]
            a.save()

    # Do roles
    roles = atty["roles"]
    if len(roles) == 0:
        roles = [{"role": Role.UNKNOWN, "date_action": None}]

    # Delete the old roles, replace with new.
    Role.objects.filter(attorney=a, party=p, docket=d).delete()
    Role.objects.bulk_create(
        [
            Role(attorney=a, party=p, docket=d, **atty_role)
            for atty_role in roles
        ]
    )
    return a.pk


def update_case_names(d, new_case_name):
    """Update the case name fields if applicable.

    This is a more complex than you'd think at first, and has resulted in at
    least two live bugs. The existing dockets and the new data can each have
    one of three values:

     - A valid case name
     - Unknown Case Title (UCT)
     - ""

    So here's a matrix for what to do:

                                       new_case_name
                       +------------+-----------------+-----------------+
                       |   x v. y   |      UCT        |      blank      |
             +---------+------------+-----------------+-----------------+
             | x v. y  |   Update   |    No update    |    No update    |
             +---------+------------+-----------------+-----------------+
      docket |  UCT    |   Update   |  Same/Whatever  |    No update    |
             +---------+------------+-----------------+-----------------+
             |  blank  |   Update   |     Update      |  Same/Whatever  |
             +---------+------------+-----------------+-----------------+

    :param d: The docket object to update or ignore
    :param new_case_name: The incoming case name
    :returns d
    """
    uct = "Unknown Case Title"
    if not new_case_name:
        return d
    if new_case_name == uct and d.case_name != "":
        return d

    d.case_name = new_case_name
    d.case_name_short = cnt.make_case_name_short(d.case_name)
    return d


def update_docket_metadata(d: Docket, docket_data: Dict[str, Any]) -> Docket:
    """Update the Docket object with the data from Juriscraper.

    Works on either docket history report or docket report (appellate
    or district) results.
    """
    d = update_case_names(d, docket_data["case_name"])
    mark_ia_upload_needed(d, save_docket=False)
    d.docket_number = docket_data["docket_number"] or d.docket_number
    d.date_filed = docket_data.get("date_filed") or d.date_filed
    d.date_last_filing = (
        docket_data.get("date_last_filing") or d.date_last_filing
    )
    d.date_terminated = docket_data.get("date_terminated") or d.date_terminated
    d.cause = docket_data.get("cause") or d.cause
    d.nature_of_suit = docket_data.get("nature_of_suit") or d.nature_of_suit
    d.jury_demand = docket_data.get("jury_demand") or d.jury_demand
    d.jurisdiction_type = (
        docket_data.get("jurisdiction") or d.jurisdiction_type
    )
    d.mdl_status = docket_data.get("mdl_status") or d.mdl_status
    lookup_judge_by_full_name_and_set_attr(
        d,
        "assigned_to",
        docket_data.get("assigned_to_str"),
        d.court_id,
        docket_data.get("date_filed"),
    )
    d.assigned_to_str = docket_data.get("assigned_to_str") or ""
    lookup_judge_by_full_name_and_set_attr(
        d,
        "referred_to",
        docket_data.get("referred_to_str"),
        d.court_id,
        docket_data.get("date_filed"),
    )
    d.referred_to_str = docket_data.get("referred_to_str") or ""
    d.blocked, d.date_blocked = get_blocked_status(d)

    return d


def update_docket_appellate_metadata(d, docket_data):
    """Update the metadata specific to appellate cases."""
    if not any(
        [
            docket_data.get("originating_court_information"),
            docket_data.get("appeal_from"),
            docket_data.get("panel"),
        ]
    ):
        # Probably not appellate.
        return d, None

    d.panel_str = ", ".join(docket_data.get("panel", [])) or d.panel_str
    d.appellate_fee_status = (
        docket_data.get("fee_status", "") or d.appellate_fee_status
    )
    d.appellate_case_type_information = (
        docket_data.get("case_type_information", "")
        or d.appellate_case_type_information
    )
    d.appeal_from_str = docket_data.get("appeal_from", "") or d.appeal_from_str

    # Do originating court information dict
    og_info = docket_data.get("originating_court_information")
    if not og_info:
        return d, None

    if og_info.get("court_id"):
        cl_id = map_pacer_to_cl_id(og_info["court_id"])
        if Court.objects.filter(pk=cl_id).exists():
            # Ensure the court exists. Sometimes PACER does weird things,
            # like in 14-1743 in CA3, where it says the court_id is 'uspci'.
            # If we don't do this check, the court ID could be invalid, and
            # our whole save of the docket fails.
            d.appeal_from_id = cl_id

    if d.originating_court_information:
        d_og_info = d.originating_court_information
    else:
        d_og_info = OriginatingCourtInformation()

    # Ensure we don't share A-Numbers, which can sometimes be in the docket
    # number field.
    docket_number = og_info.get("docket_number", "") or d_og_info.docket_number
    docket_number, _ = anonymize(docket_number)
    d_og_info.docket_number = docket_number
    d_og_info.court_reporter = (
        og_info.get("court_reporter", "") or d_og_info.court_reporter
    )
    d_og_info.date_disposed = (
        og_info.get("date_disposed") or d_og_info.date_disposed
    )
    d_og_info.date_filed = og_info.get("date_filed") or d_og_info.date_filed
    d_og_info.date_judgment = (
        og_info.get("date_judgment") or d_og_info.date_judgment
    )
    d_og_info.date_judgment_eod = (
        og_info.get("date_judgment_eod") or d_og_info.date_judgment_eod
    )
    d_og_info.date_filed_noa = (
        og_info.get("date_filed_noa") or d_og_info.date_filed_noa
    )
    d_og_info.date_received_coa = (
        og_info.get("date_received_coa") or d_og_info.date_received_coa
    )
    d_og_info.assigned_to_str = (
        og_info.get("assigned_to") or d_og_info.assigned_to_str
    )
    d_og_info.ordering_judge_str = (
        og_info.get("ordering_judge") or d_og_info.ordering_judge_str
    )

    if not all([d.appeal_from_id, d_og_info.date_filed]):
        # Can't do judge lookups. Call it quits.
        return d, d_og_info

    lookup_judge_by_full_name_and_set_attr(
        d_og_info,
        "assigned_to",
        og_info.get("assigned_to"),
        d.appeal_from_id,
        d_og_info.date_filed,
    )
    lookup_judge_by_full_name_and_set_attr(
        d_og_info,
        "ordering_judge",
        og_info.get("ordering_judge"),
        d.appeal_from_id,
        d_og_info.date_filed,
    )

    return d, d_og_info


def get_order_of_docket(docket_entries):
    """Determine whether the docket is ascending or descending or whether
    that is knowable.
    """
    order = None
    for _, de, nxt in previous_and_next(docket_entries):
        try:
            current_num = int(de["document_number"])
            nxt_num = int(nxt["document_number"])
        except (TypeError, ValueError):
            # One or the other can't be cast to an int. Continue until we have
            # two consecutive ints we can compare.
            continue

        if current_num == nxt_num:
            # Not sure if this is possible. No known instances in the wild.
            continue
        elif current_num < nxt_num:
            order = "asc"
        elif current_num > nxt_num:
            order = "desc"
        break
    return order


def make_recap_sequence_number(
    date_filed: date | datetime, recap_sequence_index: int
) -> str:
    """Make a sequence number using a date and index.

    :param date_filed: The entry date_filed used to make the sequence number.
    :param recap_sequence_index: This index will be used to populate the
    returned sequence number.
    :return: A str to use as the recap_sequence_number
    """
    template = "%s.%03d"
    return template % (
        date_filed.isoformat(),
        recap_sequence_index,
    )


def calculate_recap_sequence_numbers(docket_entries: list, court_id: str):
    """Figure out the RECAP sequence number values for docket entries
    returned by a parser.

    Writ large, this is pretty simple, but for some items you need to perform
    disambiguation using neighboring docket entries. For example, if you get
    the following docket entries, you need to use the neighboring items to
    figure out which is first:

           Date     | No. |  Description
        2014-01-01  |     |  Some stuff
        2014-01-01  |     |  More stuff
        2014-01-02  |  1  |  Still more

    For those first two items, you have the date, but that's it. No numbers,
    no de_seqno, no nuthin'. The way to handle this is to start by ensuring
    that the docket is in ascending order and correct it if not. With that
    done, you can use the values of the previous items to sort out each item
    in turn.

    :param docket_entries: A list of docket entry dicts from juriscraper or
    another parser containing information about docket entries for a docket
    :param court_id: The court id to which docket entries belong, used for
    timezone conversion.
    :return None, but sets the recap_sequence_number for all items.
    """
    # Determine the sort order of the docket entries and normalize it
    order = get_order_of_docket(docket_entries)
    if order == "desc":
        docket_entries.reverse()

    # Assign sequence numbers
    for prev, de, _ in previous_and_next(docket_entries):
        current_date_filed, current_time_filed = localize_date_and_time(
            court_id, de["date_filed"]
        )
        if current_time_filed:
            current_date_filed = datetime.combine(
                current_date_filed, current_time_filed
            )
        prev_date_filed = None
        if prev is not None:
            prev_date_filed, prev_time_filed = localize_date_and_time(
                court_id, prev["date_filed"]
            )
            if prev_time_filed:
                prev_date_filed = datetime.combine(
                    prev_date_filed, prev_time_filed
                )

        if prev is not None and current_date_filed == prev_date_filed:
            # Previous item has same date. Increment the sequence number.
            de["recap_sequence_index"] = prev["recap_sequence_index"] + 1
            de["recap_sequence_number"] = make_recap_sequence_number(
                current_date_filed, de["recap_sequence_index"]
            )
            continue
        else:
            # prev is None --> First item on the list; OR
            # current is different than previous --> Changed date.
            # Take same action: Reset the index & assign it.
            de["recap_sequence_index"] = 1
            de["recap_sequence_number"] = make_recap_sequence_number(
                current_date_filed, de["recap_sequence_index"]
            )
            continue

    # Cleanup
    [de.pop("recap_sequence_index", None) for de in docket_entries]


def normalize_long_description(docket_entry):
    """Ensure that the docket entry description is normalized

    This is important because the long descriptions from the DocketHistory
    report and the Docket report vary, with the latter appending something like
    "(Entered: 01/01/2014)" on the end of every entry. Having this value means
    that our merging algorithms fail since the *only* unique thing we have for
    a unnumbered minute entry is the description itself.

    :param docket_entry: The scraped dict from Juriscraper for the docket
    entry.
    :return None (the item is modified in place)
    """
    if not docket_entry.get("description"):
        return

    # Remove the entry info from the end of the long descriptions
    desc = docket_entry["description"]
    desc = re.sub(r"(.*) \(Entered: .*\)$", r"\1", desc)

    # Remove any brackets around numbers (this happens on the DHR long
    # descriptions).
    desc = re.sub(r"\[(\d+)\]", r"\1", desc)

    docket_entry["description"] = desc


def merge_unnumbered_docket_entries(des):
    """Unnumbered docket entries come from many sources, with different data.
    This sometimes results in two docket entries when there should be one. The
    docket history report is the one source that sometimes has the long and
    the short descriptions. When this happens, we have an opportunity to put
    them back together again, deleting the duplicate items.

    :param des: A QuerySet of DocketEntries that we believe are the same.
    :return The winning DocketEntry
    """
    # Choose the earliest as the winner; delete the rest
    winner = des.earliest("date_created")
    des.exclude(pk=winner.pk).delete()
    return winner


def find_minute_entry_by_description(
    d: Docket, docket_entry: dict[str, any]
) -> tuple[DocketEntry, bool]:
    """Finds or creates a DocketEntry object based on the provided
    docket_entry dictionary.

    :param d: The related Docket object.
    :param docket_entry: The docket entry dict.
    :returns: A two-tuple containing the DocketEntry object and a boolean
    indicating whether the DocketEntry object was created or not.
    """
    normalize_long_description(docket_entry)
    query = Q()
    if docket_entry.get("description"):
        query |= Q(description=docket_entry["description"])
    if docket_entry.get("short_description"):
        query |= Q(
            recap_documents__description=docket_entry["short_description"]
        )

    date_filed, time_filed = localize_date_and_time(
        d.court.pk, docket_entry["date_filed"]
    )
    # Query by date_filed by default.
    query_date = Q(date_filed=date_filed)
    # If time_filed is available, use it too.
    if time_filed:
        query_date = Q(date_filed=date_filed, time_filed=time_filed)

    des = DocketEntry.objects.filter(
        query,
        query_date,
        docket=d,
        entry_number=docket_entry["document_number"],
    )
    count = des.count()
    if count == 0:
        de = DocketEntry(
            docket=d, entry_number=docket_entry["document_number"]
        )
        de_created = True
    elif count == 1:
        de = des[0]
        de_created = False
    else:
        logger.warning(
            "Multiple docket entries returned for unnumbered docket "
            "entry on date: %s while processing %s. Attempting merge",
            docket_entry["date_filed"],
            d,
        )
        # There's so little metadata with unnumbered des that if there's
        # more than one match, we can just select the oldest as canonical.
        de = merge_unnumbered_docket_entries(des)
        de_created = False

    return de, de_created


def get_or_make_docket_entry(d, docket_entry):
    """Lookup or create a docket entry to match the one that was scraped.

    :param d: The docket we expect to find it in.
    :param docket_entry: The scraped dict from Juriscraper for the docket
    entry.
    :return Tuple of (de, de_created) or None, where:
     - de is the DocketEntry object
     - de_created is a boolean stating whether de was created or not
     - None is returned when things fail.
    """
    if docket_entry["document_number"]:
        with transaction.atomic():
            # In order to create a lock, we need to retrieve the docket using
            # select_for_update
            docket = Docket.objects.select_for_update().get(pk=d.pk)
            try:
                de = DocketEntry.objects.get(
                    docket=docket, entry_number=docket_entry["document_number"]
                )
                de_created = False
            except DocketEntry.DoesNotExist:
                de = DocketEntry.objects.create(
                    docket=docket, entry_number=docket_entry["document_number"]
                )
                de_created = True
            except DocketEntry.MultipleObjectsReturned:
                logger.error(
                    "Multiple docket entries found for document "
                    "entry number '%s' while processing '%s'",
                    docket_entry["document_number"],
                    d,
                )
                return None
    else:
        # Unnumbered entry. The only thing we can be sure we have is a
        # date. Try to find it by date and description (short or long)
        de, de_created = find_minute_entry_by_description(d, docket_entry)

    return de, de_created


def save_docket_entry_and_rd(
    content_updated: bool,
    d: Docket,
    de: DocketEntry,
    de_created: bool,
    docket_entry: dict[str, any],
    des_returned: list[DocketEntry],
    known_filing_dates: list[date],
    rds_created: list[RECAPDocument],
    tags: list[Tag] | None,
) -> bool | str:
    """Update or create a docket entry and associated RECAPDocument based on
    the data in the docket_entry dict.

    :param content_updated: Whether the content of the docket entry has been created.
    :param d: The Docket instance related to the DocketEntry and RECAPDocument.
    :param de: The DocketEntry instance to be updated.
    :param de_created: Whether the DocketEntry instance is newly created.
    :param docket_entry: A dict containing the DocketEntry date to update.
    :param des_returned: List of DocketEntry objects returned after processing.
    :param known_filing_dates: List of known filing dates related.
    :param rds_created: List of RECAPDocument objects created.
    :param tags: List of Tag instances to be associated with the DocketEntry
    and RECAPDocument.
    :return: content_updated or a string saying the parent for loop to continue
    """

    de.description = docket_entry["description"] or de.description
    date_filed, time_filed = localize_date_and_time(
        de.docket.court.pk, docket_entry["date_filed"]
    )
    if not time_filed:
        # If not time data is available, compare if date_filed changed if
        # so restart time_filed to None, otherwise keep the current time.
        if de.date_filed != docket_entry["date_filed"]:
            de.time_filed = None
    else:
        de.time_filed = time_filed
    de.date_filed = date_filed
    de.pacer_sequence_number = (
        docket_entry.get("pacer_seq_no") or de.pacer_sequence_number
    )
    de.recap_sequence_number = docket_entry["recap_sequence_number"]
    des_returned.append(de)
    de.save()
    if tags:
        for tag in tags:
            tag.tag_object(de)

    if de_created:
        content_updated = True
        known_filing_dates.append(de.date_filed)

    # Then make the RECAPDocument object. Try to find it. If we do, update
    # the pacer_doc_id field if it's blank. If we can't find it, create it
    # or throw an error.
    params = {
        "docket_entry": de,
        # Normalize to "" here. Unsure why, but RECAPDocuments have a
        # char field for this field while DocketEntries have a integer
        # field.
        "document_number": docket_entry["document_number"] or "",
    }
    if not docket_entry["document_number"] and docket_entry.get(
        "short_description"
    ):
        params["description"] = docket_entry["short_description"]

    if docket_entry.get("attachment_number"):
        params["document_type"] = RECAPDocument.ATTACHMENT
        params["attachment_number"] = docket_entry["attachment_number"]
    else:
        params["document_type"] = RECAPDocument.PACER_DOCUMENT

    appellate_court_ids = (
        Court.federal_courts.appellate_pacer_courts().values_list(
            "pk", flat=True
        )
    )

    # Unlike district and bankr. dockets, where you always have a main
    # RD and can optionally have attachments to the main RD, Appellate
    # docket entries can either they *only* have a main RD (with no
    # attachments) or they *only* have attachments (with no main doc).
    # Unfortunately, when we ingest a docket, we don't know if the entries
    # have attachments, so we begin by assuming they don't and create
    # main RDs for each entry. Later, if/when we get attachment pages for
    # particular entries, we convert the main documents into attachment
    # RDs. The check here ensures that if that happens for a particular
    # entry, we avoid creating the main RD a second+ time when we get the
    # docket sheet a second+ time.
    if de_created is False and d.court.pk in appellate_court_ids:
        appellate_rd_att_exists = de.recap_documents.filter(
            document_type=RECAPDocument.ATTACHMENT
        ).exists()
        if appellate_rd_att_exists:
            params["document_type"] = RECAPDocument.ATTACHMENT
    try:
        rd = RECAPDocument.objects.get(**params)
    except RECAPDocument.DoesNotExist:
        try:
            rd = RECAPDocument.objects.create(
                pacer_doc_id=docket_entry["pacer_doc_id"],
                is_available=False,
                **params,
            )
        except ValidationError:
            # Happens from race conditions.
            # continue
            return "Continue"
        rds_created.append(rd)
    except RECAPDocument.MultipleObjectsReturned:
        logger.info(
            "Multiple recap documents found for document entry number'%s' "
            "while processing '%s'" % (docket_entry["document_number"], d)
        )
        # continue
        return "Continue"

    rd.pacer_doc_id = rd.pacer_doc_id or docket_entry["pacer_doc_id"]
    rd.description = docket_entry.get("short_description") or rd.description
    try:
        rd.save()
    except ValidationError:
        # Happens from race conditions.
        # continue
        return "Continue"
    if tags:
        for tag in tags:
            tag.tag_object(rd)

    return content_updated


def add_docket_entries(
    d: Docket,
    docket_entries: list[dict[str, any]],
    tags: list[Tag] | None = None,
    order_by: str | None = None,
):
    """Update or create the docket entries and documents.

    :param d: The docket object to add things to and use for lookups.
    :param docket_entries: A list of dicts containing docket entry data.
    :param tags: A list of tag objects to apply to the recap documents and
    docket entries created or updated in this function.
    :param order_by: Optional, whether the docket entries are ordered by
    date_filed or date_entered
    :returns tuple of a list of created or existing
    DocketEntry objects,  a list of RECAPDocument objects created, whether
    any docket entry was created.
    """
    # Remove items without a date filed value.
    docket_entries = [de for de in docket_entries if de.get("date_filed")]

    rds_created = []
    des_returned = []
    content_updated = False
    calculate_recap_sequence_numbers(docket_entries, d.court_id)
    known_filing_dates = [d.date_last_filing]

    minute_entries_long_des = filter_long_description_minute_entries_to_merge(
        docket_entries, order_by
    )
    if minute_entries_long_des:
        # If there are minute entries with long descriptions to merge. Only
        # add/merge entries not included in minute_entries_long_des with the
        # normal method.
        docket_entries = [
            entry
            for entry in docket_entries
            if entry not in minute_entries_long_des
        ]

    # Add/merge not long description minute entries with the traditional method
    for docket_entry in docket_entries:
        response = get_or_make_docket_entry(d, docket_entry)
        if response is None:
            continue
        else:
            de, de_created = response[0], response[1]

        response = save_docket_entry_and_rd(
            content_updated,
            d,
            de,
            de_created,
            docket_entry,
            des_returned,
            known_filing_dates,
            rds_created,
            tags,
        )
        if response == "Continue":
            continue
        content_updated = response

    # Add/merge long description minute entries
    if minute_entries_long_des:
        (
            des_returned,
            rds_created,
            content_updated,
            known_filing_dates,
        ) = merge_long_description_minute_entries(
            content_updated,
            d,
            des_returned,
            known_filing_dates,
            minute_entries_long_des,
            order_by,
            rds_created,
            tags,
        )

    known_filing_dates = set(filter(None, known_filing_dates))
    if known_filing_dates:
        Docket.objects.filter(pk=d.pk).update(
            date_last_filing=max(known_filing_dates)
        )

    return des_returned, rds_created, content_updated


def filter_long_description_minute_entries_to_merge(
    docket_entries: list[dict[str, any]], order_by: str | None = None
) -> list[dict[str, any]]:
    """
    Filters and returns minute entries with long descriptions from the given
    docket_entries.

    :param docket_entries: A list of docket entries to filter.
    :param order_by: Optional, whether the docket entries are ordered by
    date_filed or date_entered.
    :return: A list of filtered minute entries with long descriptions to merge.
    """

    # Filter minute entries with long descriptions, avoid docket history
    # report entries, exclude entries with no date_entered.
    minute_entries_long_des_date_entered = [
        entry
        for entry in docket_entries
        if entry["description"]
        and entry.get("date_entered")
        and not entry["document_number"]
        and not entry["pacer_doc_id"]
        and not entry.get("short_description")
    ]

    # If the docket sheet is ordered by "date_entered", we can try to
    # merge minute entries without date_entered, since the entry date_filed
    # equals to the date_entered.
    minute_entries_long_des_not_date_entered = []
    if order_by == "date_entered":
        minute_entries_long_des_not_date_entered = [
            entry
            for entry in docket_entries
            if entry["description"]
            and not entry.get("date_entered")
            and not entry["document_number"]
            and not entry["pacer_doc_id"]
            and not entry.get("short_description")
        ]

    minute_entries_long_des = (
        minute_entries_long_des_date_entered
        + minute_entries_long_des_not_date_entered
    )

    return minute_entries_long_des


def merge_long_description_minute_entries(
    content_updated: bool,
    d: Docket,
    des_returned: list[DocketEntry],
    known_filing_dates: list[date],
    minute_entries_long_des: list[dict[str, any]],
    order_by: str | None,
    rds_created: list[RECAPDocument],
    tags: list[Tag],
) -> tuple[list[DocketEntry], list[RECAPDocument], bool, list[date]]:
    """Merges short and long description minute entries in a given docket.

    :param content_updated: Flag indicating whether a new docket entry has been
    created.
    :param d: A Docket object for which minute entries are being merged.
    :param des_returned: List of returned DocketEntry objects.
    :param known_filing_dates: List of known filing dates.
    :param minute_entries_long_des: List of dicts containing the long
     description minute entries.
    :param order_by: Ordering method, can be either "date_entered",
     "date_filed" or None.
    :param rds_created: List of RECAPDocument objects that were created.
    :param tags: List of Tag objects.

    :return: A four-tuple with list of returned DocketEntry objects, list of
      RECAPDocument objects created, whether a new docket entry was created
      and a list of known filing dates.
    """

    # Get unique dates on which try to merge entries.
    unique_dates = []
    for entry in minute_entries_long_des:
        date_entered = entry.get("date_entered")
        if entry.get("ordered_by") == "date_entered":
            date_entered = entry["date_filed"]
        if not date_entered:
            continue
        if date_entered not in unique_dates:
            unique_dates.append(date_entered)

    short_description_entries = {}
    long_description_entries = {}

    de_created = False
    query = Q(recap_documents__pacer_doc_id="")
    for date_entered in unique_dates:
        minute_entries_to_merge = DocketEntry.objects.filter(
            query,
            docket=d,
            date_filed=date_entered,
            entry_number=None,
            description="",
        ).order_by("recap_sequence_number")
        short_description_entries[date_entered] = list(minute_entries_to_merge)

        # Filter entries by date.
        if order_by == "date_entered":
            long_description_entries[date_entered] = [
                entry
                for entry in minute_entries_long_des
                if entry["date_filed"] == date_entered
            ]
        else:
            long_description_entries[date_entered] = [
                entry
                for entry in minute_entries_long_des
                if entry["date_entered"] == date_entered
            ]

        entries_to_merge, entries_to_add = look_for_minute_entries_matches(
            d,
            short_description_entries[date_entered],
            long_description_entries[date_entered],
            order_by,
        )

        with transaction.atomic():
            docket = Docket.objects.select_for_update().get(pk=d.pk)
            for entry_to_merge in entries_to_merge:
                de = DocketEntry.objects.get(
                    docket=docket, pk=entry_to_merge[0]
                )
                docket_entry = entry_to_merge[1]
                normalize_long_description(docket_entry)
                response = save_docket_entry_and_rd(
                    content_updated,
                    d,
                    de,
                    de_created,
                    docket_entry,
                    des_returned,
                    known_filing_dates,
                    rds_created,
                    tags,
                )
                if response == "Continue":
                    continue
                content_updated = response

            for docket_entry in entries_to_add:
                de = DocketEntry.objects.create(
                    docket=docket, entry_number=docket_entry["document_number"]
                )
                de_created = True
                normalize_long_description(docket_entry)
                response = save_docket_entry_and_rd(
                    content_updated,
                    d,
                    de,
                    de_created,
                    docket_entry,
                    des_returned,
                    known_filing_dates,
                    rds_created,
                    tags,
                )
                if response == "Continue":
                    continue
                content_updated = response

    return des_returned, rds_created, content_updated, known_filing_dates


def look_for_minute_entries_matches(
    d: Docket,
    short_des_entries: list[DocketEntry],
    long_des_entries: list[dict[str, any]],
    order_by: str | None,
) -> tuple[list[tuple[int, dict[str, any]]], list[dict[str, any]]]:
    """This method looks for matching minute entries in the given short and
    long description lists and returns the entries to be merged and the entries
    to be added.

    :param d: The Docket object to which the minute entries belong.
    :param short_des_entries: A list of short description minute entries.
    :param long_des_entries: A list of long description minute entries.
    :param order_by: A string indicating the order for merging the entries.
    Can be 'date_entered', 'date_filed' or None.

    :return: A two-tuple of, a list of tuples where each tuple contains the pk
    of the short description entry and its corresponding long description entry,
    a list of long description entries that have no matching short description
    entry and should be added to the Docket.
    """

    entries_to_merge = []
    short_descriptions = [
        short_de.recap_documents.all()[0].description
        for short_de in short_des_entries
    ]
    short_descriptions_equal = all(
        x == short_descriptions[0] for x in short_descriptions
    )
    if len(short_des_entries) == len(long_des_entries):
        # Same number of minute entries in both sides.
        if len(long_des_entries) == 1:
            # Case 1: One entry on both sides, merge it directly if date_filed
            # and date_entered are the same in order to guarantee a proper merge
            if (
                order_by == "date_filed" or order_by is None
            ) and long_des_entries[0].get("date_entered") == long_des_entries[
                0
            ][
                "date_filed"
            ]:
                entry = (short_des_entries[0].pk, long_des_entries[0])
                entries_to_merge.append(entry)

        # Case 2: Same number of entries and short descriptions are the same.
        # Merge them directly.
        elif short_descriptions and short_descriptions_equal:
            for i, short_de in enumerate(short_des_entries):
                entry = (short_de.pk, long_des_entries[i])
                entries_to_merge.append(entry)

        elif short_descriptions and not short_descriptions_equal:
            # Short descriptions are not the same, use order as helper to merge
            sorted_long_des = sorted(
                long_des_entries, key=lambda x: x["recap_sequence_number"]
            )
            if order_by == "date_entered":
                # Case 3: Short descriptions are not the same. Use date_entered
                # order as helper, merge them.
                for i, short_de in enumerate(short_des_entries):
                    entry = (short_de.pk, sorted_long_des[i])
                    entries_to_merge.append(entry)

            elif order_by == "date_filed" or order_by is None:
                # date_filed or None order, confirm each date_entered dates is
                # equal to its date_filed
                date_entered_equal = all(
                    entry.get("date_entered") == entry["date_filed"]
                    for entry in long_des_entries
                )
                if date_entered_equal:
                    # Case 4: If all date_filed equals their date_entered,
                    # merge them.
                    for i, short_de in enumerate(short_des_entries):
                        entry = (short_de.pk, sorted_long_des[i])
                        entries_to_merge.append(entry)

        matched_entries = [x[1] for x in entries_to_merge]
        no_matched_entries = [
            x for x in long_des_entries if x not in matched_entries
        ]
        # Try to find matches in not_matches_entries using word matching as a
        # fallback, append matches to previous matches.
        entries_to_merge_word_matching, no_matched_entries = do_word_matching(
            short_des_entries, no_matched_entries
        )
        entries_to_merge = entries_to_merge + entries_to_merge_word_matching

    elif short_des_entries:
        # Case 5: Not the same number of minute entries in both sides.
        # We try word marching.
        entries_to_merge, no_matched_entries = do_word_matching(
            short_des_entries, long_des_entries
        )
    else:
        # Case 6: No short description entries to merge in, add new entries.
        no_matched_entries = long_des_entries

    entries_to_add = []
    for docket_entry in no_matched_entries:
        # Confirm that no matching entries do not exist yet.
        de, de_created = find_minute_entry_by_description(d, docket_entry)
        if de_created:
            entries_to_add.append(docket_entry)

        # No need to return de, since de description and date is already the
        # same, no need to update it.
    return entries_to_merge, entries_to_add


def do_word_matching(
    short_des_entries: list[DocketEntry],
    long_des_entries: list[dict[str, any]],
) -> tuple[list[tuple[int, dict[str, any]]], list[dict[str, any]]]:
    """This method performs word matching between short description minute
    entries and long description minute entries to find potential matches and returns
    the entries to be merged and the entries to be added.

    :param short_des_entries: A list of short description minute entries.
    :param long_des_entries: A list of long description minute entries.

    :return: A two-tuple of entries to merge and entries to add.
    """

    entries_to_merge = []
    matched_entries = {}
    long_des_matched = []

    for short_des_entry in short_des_entries:
        matched_entries[short_des_entry.pk] = []
        for long_des_entry in long_des_entries:
            # Check if there is a match between the short and long description
            # entries
            short_description = short_des_entry.recap_documents.all()[
                0
            ].description
            matched = check_if_there_is_a_match(
                short_description, long_des_entry["description"]
            )
            if matched:
                matched_entries[short_des_entry.pk].append(long_des_entry)

    # Reduce matched entries after removing match conflicts.
    matches_after_reduce = reduce_matched_entries(matched_entries)
    for short_des_pk, matches in matches_after_reduce.items():
        if len(matches) == 1:
            # If there is only one matched long description entry, add it to
            # the entries_to_merge list
            entries_to_merge.append((short_des_pk, matches[0]))
            long_des_matched.append(matches[0])

    # Find entries that have no match and should be added
    entries_to_add = [x for x in long_des_entries if x not in long_des_matched]
    return entries_to_merge, entries_to_add


def reduce_matched_entries(
    matched_entries: dict[int, list[dict[str, any]]]
) -> dict[int, list[dict[str, any]]]:
    """This method reduces the matched entries dictionary by ensuring that
    each short description entry has at most one matching long description
    entry.
    The method solves conflicts by removing duplicate matches and updates the
    dictionary accordingly

    :param: matched_entries: A dictionary where the keys are the pk of short
    description minute entries, and the values are lists of matching long
    description minute entries.

    :return: The matched_entries dict after solving match conflicts.
    """

    matches_after_reduce = dict(matched_entries)
    single_element_keys = set()

    # Find entries with a single element in their lists
    for key, value in matches_after_reduce.items():
        if len(value) == 1:
            single_element_keys.add(key)

    # Process entries with single elements
    while single_element_keys:
        single_element_key = single_element_keys.pop()
        single_element = matches_after_reduce[single_element_key][0]

        # Remove the element from other entries lists
        for key, value in matches_after_reduce.items():
            if key != single_element_key and single_element in value:
                removed = False
                if not len(value) == 1:
                    value.remove(single_element)
                    removed = True
                if len(value) == 1 and removed:
                    single_element_keys.add(key)
    return matches_after_reduce


def check_if_there_is_a_match(
    short_description: str,
    long_description: str,
) -> bool:
    """This method checks if there is a match between a long description
    minute entry and a short description minute entry based on the number of
    matched words in their descriptions.

    :param short_description: The short description minute entry.
    :param long_description: The long description minute entry.

    :return: True if the long description entry and the short description
    entry are considered a match based on their matched words count, False otherwise.
    """

    matched_words_count = count_words_in_text(
        short_description, long_description
    )
    if matched_words_count:
        count_short_words = len(clean_and_split_words(short_description))
        half_words = round(count_short_words / 2)
        separator_count = short_description.count("AND")
        if "AND" in short_description or "-" in short_description:
            if separator_count == 1 or separator_count == 0:
                separator_count = 2
            half_words = round(half_words / separator_count)
        if matched_words_count >= half_words:
            return True
    return False


def count_words_in_text(short_text: str, long_text: str) -> int:
    """This method counts the number of words from the short text that are
    present in the long text. It ensures that each unique word from the short
    text is counted only once.

    :param short_text: The short text to check for matching words.
    :param long_text: The long text to compare against the short text.

    :return: The number of unique words from the short text that are present in
    the long text.
    """

    short_words = clean_and_split_words(short_text)
    long_words = clean_and_split_words(long_text)
    long_set = set(long_words)

    # Initialize a counter for the number of matching words
    count = 0
    unique_words = {}
    # Iterate over the words in the short text and count how many are in the
    # long text
    for word in short_words:
        unique_word = unique_words.get(word)
        if word in long_set and not unique_word:
            unique_words[word] = True
            count += 1

    return count


def clean_and_split_words(text: str) -> list[str]:
    """This method cleans a given text by converting it to lowercase and
    removing specific characters and stop words, the cleaned text is then
    split into tokens.

    :param text: The input text to be cleaned and split.
    :return: A list of cleaned and split tokens from the input text.
    """

    cleaned_text = text.lower()
    cleaned_text = (
        cleaned_text.replace(".", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("*", " ")
        .replace("<", " ")
        .replace("/", " ")
    )
    tokens = [word for word in cleaned_text.split() if word not in STOP_WORDS]
    return tokens


def check_json_for_terminated_entities(parties) -> bool:
    """Check the parties and attorneys to find if any terminated entities

    If so, we can assume that the user checked the box for "Terminated Parties"
    before running their docket report. If not, we can assume they didn't.

    :param parties: List of party dicts, as returned by Juriscraper.
    :returns boolean indicating whether any parties had termination dates.
    """
    for party in parties:
        if party.get("date_terminated"):
            return True
        for atty in party.get("attorneys", []):
            terminated_role = {a["role"] for a in atty["roles"]} & {
                Role.TERMINATED,
                Role.SELF_TERMINATED,
            }
            if terminated_role:
                return True
    return False


def get_terminated_entities(d):
    """Check the docket to identify if there were any terminated parties or
    attorneys. If so, return their IDs.

    :param d: A docket object to investigate.
    :returns (parties, attorneys): A tuple of two sets. One for party IDs, one
    for attorney IDs.
    """
    # This will do five queries at most rather than doing potentially hundreds
    # on cases with many parties.
    parties = (
        d.parties.prefetch_related(
            Prefetch(
                "party_types",
                queryset=PartyType.objects.filter(docket=d)
                .exclude(date_terminated=None)
                .distinct()
                .only("pk"),
                to_attr="party_types_for_d",
            ),
            Prefetch(
                "attorneys",
                queryset=Attorney.objects.filter(roles__docket=d)
                .distinct()
                .only("pk"),
                to_attr="attys_in_d",
            ),
            Prefetch(
                "attys_in_d__roles",
                queryset=Role.objects.filter(
                    docket=d, role__in=[Role.SELF_TERMINATED, Role.TERMINATED]
                )
                .distinct()
                .only("pk"),
                to_attr="roles_for_atty",
            ),
        )
        .distinct()
        .only("pk")
    )
    terminated_party_ids = set()
    terminated_attorney_ids = set()
    for party in parties:
        for _ in party.party_types_for_d:
            # PartyTypes are filtered to terminated objects. Thus, if
            # any exist, we know it's a terminated party.
            terminated_party_ids.add(party.pk)
            break
        for atty in party.attys_in_d:
            for _ in atty.roles_for_atty:
                # Roles are filtered to terminated roles. Thus, if any hits, we
                # know we have terminated attys.
                terminated_attorney_ids.add(atty.pk)
                break
    return terminated_party_ids, terminated_attorney_ids


def normalize_attorney_roles(parties):
    """Clean up the attorney roles for all parties.

    We do this fairly early in the process because we need to know if
    there are any terminated attorneys before we can start
    adding/removing content to/from the database. By normalizing
    early, we ensure we have good data for that sniffing.

    A party might be input with an attorney such as:

        {
            'name': 'William H. Narwold',
            'contact': ("1 Corporate Center\n",
                        "20 Church Street\n",
                        "17th Floor\n",
                        "Hartford, CT 06103\n",
                        "860-882-1676\n",
                        "Fax: 860-882-1682\n",
                        "Email: bnarwold@motleyrice.com"),
            'roles': ['LEAD ATTORNEY',
                      'TERMINATED: 03/12/2013'],
        }

    The role attribute will be cleaned up to be:

        'roles': [{
            'role': Role.ATTORNEY_LEAD,
            'date_action': None,
            'role_raw': 'LEAD ATTORNEY',
        }, {
            'role': Role.TERMINATED,
            'date_action': date(2013, 3, 12),
            'role_raw': 'TERMINATED: 03/12/2013',
        }

    :param parties: The parties dict from Juriscraper.
    :returns None; editing happens in place.

    """
    for party in parties:
        for atty in party.get("attorneys", []):
            roles = [normalize_attorney_role(r) for r in atty["roles"]]
            roles = remove_duplicate_dicts(roles)
            atty["roles"] = roles


def disassociate_extraneous_entities(
    d, parties, parties_to_preserve, attorneys_to_preserve
):
    """Disassociate any parties or attorneys no longer in the latest info.

     - Do not delete parties or attorneys, just allow them to be orphaned.
       Later, we can decide what to do with these, but keeping them around at
       least lets us have them later if we need them.

     - Sort out if terminated parties were included in the new data. If so,
       they'll be automatically preserved (because they would have been
       updated). If not, find the old terminated parties on the docket, and
       prevent them from getting disassociated.

     - If a party is terminated, do not delete their attorneys even if their
       attorneys are not listed as terminated.

    :param d: The docket to interrogate and act upon.
    :param parties: The parties dict that was scraped, and which we inspect to
    check if terminated parties were included.
    :param parties_to_preserve: A set of party IDs that were updated or created
    while updating the docket.
    :param attorneys_to_preserve: A set of attorney IDs that were updated or
    created while updating the docket.
    """
    new_has_terminated_entities = check_json_for_terminated_entities(parties)
    if not new_has_terminated_entities:
        # No terminated data in the JSON. Check if we have any in the DB.
        terminated_parties, terminated_attorneys = get_terminated_entities(d)
        if any([terminated_parties, terminated_attorneys]):
            # The docket currently has terminated entities, but new info
            # doesn't, indicating that the user didn't request it. Thus, delete
            # any entities that weren't just created/updated and that aren't in
            # the list of terminated entities.
            parties_to_preserve = parties_to_preserve | terminated_parties
            attorneys_to_preserve = (
                attorneys_to_preserve | terminated_attorneys
            )
    else:
        # The terminated parties are already included in the entities to
        # preserve, so just create an empty variable for this.
        terminated_parties = set()

    # Disassociate extraneous parties from the docket.
    PartyType.objects.filter(
        docket=d,
    ).exclude(
        party_id__in=parties_to_preserve,
    ).delete()

    # Disassociate extraneous attorneys from the docket and parties.
    Role.objects.filter(
        docket=d,
    ).exclude(
        # Don't delete attorney roles for attorneys we're preserving.
        attorney_id__in=attorneys_to_preserve,
    ).exclude(
        # Don't delete attorney roles for parties we're preserving b/c
        # they were terminated.
        party_id__in=terminated_parties,
    ).delete()


@transaction.atomic
# Retry on transaction deadlocks; see #814.
@retry(OperationalError, tries=2, delay=1, backoff=1, logger=logger)
def add_parties_and_attorneys(d, parties):
    """Add parties and attorneys from the docket data to the docket.

    :param d: The docket to update
    :param parties: The parties to update the docket with, with their
    associated attorney objects. This is typically the
    docket_data['parties'] field.
    :return: None

    """
    if not parties:
        # Exit early if no parties. Some dockets don't have any due to user
        # preference, and if we don't bail early, we risk deleting everything
        # we have.
        return

    # Recall that Python is pass by reference. This means that if we mutate
    # the parties variable in this function and then retry this function (note
    # the decorator it has), the second time this function runs, it will not be
    # run with the initial value of the parties variable, but will instead be
    # run with the mutated value! That will crash because the mutated variable
    # no longer has the correct shape as it did when it was first passed.
    # ∴, make a copy of parties as a first step, so that retries work.
    local_parties = deepcopy(parties)

    normalize_attorney_roles(local_parties)

    updated_parties = set()
    updated_attorneys = set()
    for party in local_parties:
        ps = Party.objects.filter(
            name=party["name"], party_types__docket=d
        ).distinct()
        count = ps.count()
        if count == 0:
            try:
                p = Party.objects.create(name=party["name"])
            except IntegrityError:
                # Race condition. Object was created after our get and before
                # our create. Try to get it again.
                ps = Party.objects.filter(
                    name=party["name"], party_types__docket=d
                ).distinct()
                count = ps.count()
        if count == 1:
            p = ps[0]
        elif count >= 2:
            p = ps.earliest("date_created")
        updated_parties.add(p.pk)

        # If the party type doesn't exist, make a new one.
        pts = p.party_types.filter(docket=d, name=party["type"])
        criminal_data = party.get("criminal_data")
        update_dict = {
            "extra_info": party.get("extra_info", ""),
            "date_terminated": party.get("date_terminated"),
        }
        if criminal_data:
            update_dict["highest_offense_level_opening"] = criminal_data[
                "highest_offense_level_opening"
            ]
            update_dict["highest_offense_level_terminated"] = criminal_data[
                "highest_offense_level_terminated"
            ]
        if pts.exists():
            pts.update(**update_dict)
            pt = pts[0]
        else:
            pt = PartyType.objects.create(
                docket=d, party=p, name=party["type"], **update_dict
            )

        # Criminal counts and complaints
        if criminal_data and criminal_data["counts"]:
            CriminalCount.objects.filter(party_type=pt).delete()
            CriminalCount.objects.bulk_create(
                [
                    CriminalCount(
                        party_type=pt,
                        name=criminal_count["name"],
                        disposition=criminal_count["disposition"],
                        status=CriminalCount.normalize_status(
                            criminal_count["status"]
                        ),
                    )
                    for criminal_count in criminal_data["counts"]
                ]
            )

        if criminal_data and criminal_data["complaints"]:
            CriminalComplaint.objects.filter(party_type=pt).delete()
            CriminalComplaint.objects.bulk_create(
                [
                    CriminalComplaint(
                        party_type=pt,
                        name=complaint["name"],
                        disposition=complaint["disposition"],
                    )
                    for complaint in criminal_data["complaints"]
                ]
            )

        # Attorneys
        for atty in party.get("attorneys", []):
            updated_attorneys.add(add_attorney(atty, p, d))

    disassociate_extraneous_entities(
        d, local_parties, updated_parties, updated_attorneys
    )


@transaction.atomic
def add_bankruptcy_data_to_docket(d: Docket, metadata: Dict[str, str]) -> None:
    """Add bankruptcy data to the docket from the claims data, RSS feeds, or
    another location.
    """
    try:
        bankr_data = d.bankruptcy_information
    except BankruptcyInformation.DoesNotExist:
        bankr_data = BankruptcyInformation(docket=d)

    fields = [
        "date_converted",
        "date_last_to_file_claims",
        "date_last_to_file_govt",
        "date_debtor_dismissed",
        "chapter",
        "trustee_str",
    ]
    do_save = False
    for field in fields:
        if metadata.get(field):
            do_save = True
            setattr(bankr_data, field, metadata[field])

    if do_save:
        bankr_data.save()


def add_claim_history_entry(new_history, claim):
    """Add a document from a claim's history table to the database.

    These documents can reference docket entries or documents that only exist
    in the claims registry. Whatever the case, we just make an entry in the
    claims history table. For now we don't try to link the docket entry table
    with the claims table. It's doable, but adds complexity.

    Further, we also don't handle unnumbered claims. You can see an example of
    one of these in Juriscraper in the txeb.html example file. Here, we just
    punt on these.

    :param new_history: The history dict returned by juriscraper.
    :param claim: The claim in the database the history is associated with.
    :return None
    """
    if new_history["document_number"] is None:
        # Punt on unnumbered claims.
        return

    history_type = new_history["type"]
    common_lookup_params = {
        "claim": claim,
        "date_filed": new_history["date_filed"],
        # Sometimes missing when a docket entry type
        # doesn't have a link for some reason.
        "pacer_case_id": new_history.get("pacer_case_id", ""),
        "document_number": new_history["document_number"],
    }

    if history_type == "docket_entry":
        db_history, _ = ClaimHistory.objects.get_or_create(
            claim_document_type=ClaimHistory.DOCKET_ENTRY,
            pacer_doc_id=new_history.get("pacer_doc_id", ""),
            **common_lookup_params,
        )
        db_history.pacer_dm_id = (
            new_history.get("pacer_dm_id") or db_history.pacer_dm_id
        )
        db_history.pacer_seq_no = new_history.get("pacer_seq_no")

    else:
        db_history, _ = ClaimHistory.objects.get_or_create(
            claim_document_type=ClaimHistory.CLAIM_ENTRY,
            claim_doc_id=new_history["id"],
            attachment_number=new_history["attachment_number"],
            **common_lookup_params,
        )

    db_history.description = (
        new_history.get("description") or db_history.description
    )
    db_history.save()


@transaction.atomic
def add_claims_to_docket(d, new_claims, tag_names=None):
    """Add claims data to the docket.

    :param d: A docket object to associate claims with.
    :param new_claims: A list of claims dicts from Juriscraper.
    :param tag_names: A list of tag names to add to the claims.
    """
    for new_claim in new_claims:
        db_claim, _ = Claim.objects.get_or_create(
            docket=d, claim_number=new_claim["claim_number"]
        )
        db_claim.date_claim_modified = (
            new_claim.get("date_claim_modified")
            or db_claim.date_claim_modified
        )
        db_claim.date_original_entered = (
            new_claim.get("date_original_entered")
            or db_claim.date_original_entered
        )
        db_claim.date_original_filed = (
            new_claim.get("date_original_filed")
            or db_claim.date_original_filed
        )
        db_claim.date_last_amendment_entered = (
            new_claim.get("date_last_amendment_entered")
            or db_claim.date_last_amendment_entered
        )
        db_claim.date_last_amendment_filed = (
            new_claim.get("date_last_amendment_filed")
            or db_claim.date_last_amendment_filed
        )
        db_claim.creditor_details = (
            new_claim.get("creditor_details") or db_claim.creditor_details
        )
        db_claim.creditor_id = (
            new_claim.get("creditor_id") or db_claim.creditor_id
        )
        db_claim.status = new_claim.get("status") or db_claim.status
        db_claim.entered_by = (
            new_claim.get("entered_by") or db_claim.entered_by
        )
        db_claim.filed_by = new_claim.get("filed_by") or db_claim.filed_by
        db_claim.amount_claimed = (
            new_claim.get("amount_claimed") or db_claim.amount_claimed
        )
        db_claim.unsecured_claimed = (
            new_claim.get("unsecured_claimed") or db_claim.unsecured_claimed
        )
        db_claim.secured_claimed = (
            new_claim.get("secured_claimed") or db_claim.secured_claimed
        )
        db_claim.priority_claimed = (
            new_claim.get("priority_claimed") or db_claim.priority_claimed
        )
        db_claim.description = (
            new_claim.get("description") or db_claim.description
        )
        db_claim.remarks = new_claim.get("remarks") or db_claim.remarks
        db_claim.save()
        add_tags_to_objs(tag_names, [db_claim])
        for new_history in new_claim["history"]:
            add_claim_history_entry(new_history, db_claim)


def get_data_from_att_report(text: str, court_id: str) -> Dict[str, str]:
    att_page = AttachmentPage(map_cl_to_pacer_id(court_id))
    att_page._parse_text(text)
    att_data = att_page.data
    return att_data


def get_data_from_appellate_att_report(
    text: str, court_id: str
) -> Dict[str, str]:
    """Get attachments data from Juriscraper AppellateAttachmentPage

    :param text: The attachment page text to parse.
    :param court_id: The CourtListener court_id we're working with
    :return: The appellate attachment page data
    """
    att_page = AppellateAttachmentPage(map_cl_to_pacer_id(court_id))
    att_page._parse_text(text)
    att_data = att_page.data
    return att_data


def add_tags_to_objs(tag_names: List[str], objs: Any) -> QuerySet:
    """Add tags by name to objects

    :param tag_names: A list of tag name strings
    :type tag_names: list
    :param objs: A list of objects in need of tags
    :type objs: list
    :return: [] if no tag names, else a list of the tags created/found
    """
    if tag_names is None:
        return []

    tags = []
    for tag_name in tag_names:
        tag, _ = Tag.objects.get_or_create(name=tag_name)
        tags.append(tag)

    for tag in tags:
        for obj in objs:
            tag.tag_object(obj)
    return tags


@transaction.atomic
def merge_pacer_docket_into_cl_docket(
    d, pacer_case_id, docket_data, report, appellate=False, tag_names=None
):
    # Ensure that we set the case ID. This is needed on dockets that have
    # matching docket numbers, but that never got PACER data before. This was
    # previously rare, but since we added the FJC data to the dockets table,
    # this is now quite common.
    if not d.pacer_case_id:
        d.pacer_case_id = pacer_case_id

    d.add_recap_source()
    update_docket_metadata(d, docket_data)
    d.save()

    if appellate:
        d, og_info = update_docket_appellate_metadata(d, docket_data)
        if og_info is not None:
            og_info.save()
            d.originating_court_information = og_info

    tags = add_tags_to_objs(tag_names, [d])

    # Add the HTML to the docket in case we need it someday.
    upload_type = (
        UPLOAD_TYPE.APPELLATE_DOCKET if appellate else UPLOAD_TYPE.DOCKET
    )
    pacer_file = PacerHtmlFiles(content_object=d, upload_type=upload_type)
    pacer_file.filepath.save(
        "docket.html",  # We only care about the ext w/S3PrivateUUIDStorageTest
        ContentFile(report.response.text.encode()),
    )

    des_returned, rds_created, content_updated = add_docket_entries(
        d,
        docket_data["docket_entries"],
        tags=tags,
        order_by=docket_data.get("ordered_by"),
    )
    add_parties_and_attorneys(d, docket_data["parties"])
    process_orphan_documents(rds_created, d.court_id, d.date_filed)
    logger.info(f"Created/updated docket: {d}")
    return rds_created, content_updated


@transaction.atomic
def merge_attachment_page_data(
    court: Court,
    pacer_case_id: int,
    pacer_doc_id: int,
    document_number: int | None,
    text: str,
    attachment_dicts: List[Dict[str, Union[int, str]]],
    debug: bool = False,
) -> Tuple[List[RECAPDocument], DocketEntry]:
    """Merge attachment page data into the docket

    :param court: The court object we're working with
    :param pacer_case_id: A PACER case ID
    :param pacer_doc_id: A PACER document ID
    :param document_number: The docket entry number
    :param text: The text of the attachment page
    :param attachment_dicts: A list of Juriscraper-parsed dicts for each
    attachment.
    :param debug: Whether to do saves during this process.
    :return: A list of RECAPDocuments modified or created during the process,
    and the DocketEntry object associated with the RECAPDocuments
    :raises: RECAPDocument.MultipleObjectsReturned, RECAPDocument.DoesNotExist
    """
    try:
        params = {
            "pacer_doc_id": pacer_doc_id,
            "docket_entry__docket__court": court,
        }
        if pacer_case_id:
            params["docket_entry__docket__pacer_case_id"] = pacer_case_id
        main_rd = RECAPDocument.objects.get(**params)
    except RECAPDocument.MultipleObjectsReturned as exc:
        # Unclear how to proceed and we don't want to associate this data with
        # the wrong case. We must punt.
        raise exc
    except RECAPDocument.DoesNotExist as exc:
        # Can't find the docket to associate with the attachment metadata
        # It may be possible to go look for orphaned documents at this stage
        # and to then add them here, as we do when adding dockets. This need is
        # particularly acute for those that get free look emails and then go to
        # the attachment page.
        raise exc

    # We got the right item. Update/create all the attachments for
    # the docket entry.
    de = main_rd.docket_entry
    if document_number is None:
        # Bankruptcy or Appellate attachment page. Use the document number from
        # the Main doc
        document_number = main_rd.document_number

    if debug:
        return [], de

    # Save the old HTML to the docket entry.
    pacer_file = PacerHtmlFiles(
        content_object=de, upload_type=UPLOAD_TYPE.ATTACHMENT_PAGE
    )
    pacer_file.filepath.save(
        "attachment_page.html",  # Irrelevant b/c S3PrivateUUIDStorageTest
        ContentFile(text.encode()),
    )

    # Create/update the attachment items.
    rds_created = []
    rds_affected = []
    appellate_court_ids = (
        Court.federal_courts.appellate_pacer_courts().values_list(
            "pk", flat=True
        )
    )
    for attachment in attachment_dicts:
        sanity_checks = [
            attachment["attachment_number"],
            # Missing on sealed items.
            attachment.get("pacer_doc_id", False),
            # Missing on some restricted docs (see Juriscraper)
            attachment["page_count"] is not None,
            attachment["description"],
        ]
        if not all(sanity_checks):
            continue

        # Appellate entries with attachments don't have a main RD, transform it
        # to an attachment.
        if (
            court.pk in appellate_court_ids
            and attachment["pacer_doc_id"] == main_rd.pacer_doc_id
        ):
            main_rd.document_type = RECAPDocument.ATTACHMENT
            main_rd.attachment_number = attachment["attachment_number"]
            rd = main_rd
            created = False
        else:
            rd, created = RECAPDocument.objects.update_or_create(
                docket_entry=de,
                document_number=document_number,
                attachment_number=attachment["attachment_number"],
                document_type=RECAPDocument.ATTACHMENT,
            )

        if created:
            rds_created.append(rd)
        rds_affected.append(rd)

        for field in ["description", "pacer_doc_id"]:
            if attachment[field]:
                setattr(rd, field, attachment[field])

        # Only set page_count and file_size if they're blank, in case
        # we got the real value by measuring.
        if rd.page_count is None:
            rd.page_count = attachment["page_count"]
        if rd.file_size is None and attachment.get("file_size_str", None):
            try:
                rd.file_size = convert_size_to_bytes(
                    attachment["file_size_str"]
                )
            except ValueError:
                pass
        rd.save()

        # Do *not* do this async — that can cause race conditions.
        add_items_to_solr([rd.pk], "search.RECAPDocument")

    mark_ia_upload_needed(de.docket, save_docket=True)
    process_orphan_documents(
        rds_created, court.pk, main_rd.docket_entry.docket.date_filed
    )
    return rds_affected, de


def save_iquery_to_docket(
    self,
    iquery_data: Dict[str, str],
    d: Docket,
    tag_names: Optional[List[str]],
    add_to_solr: bool = False,
) -> Optional[int]:
    """Merge iquery results into a docket

    :param self: The celery task calling this function
    :param iquery_data: The data from a successful iquery response
    :param d: A docket object to work with
    :param tag_names: Tags to add to the items
    :param add_to_solr: Whether to save the completed docket to solr
    :return: The pk of the docket if successful. Else, None.
    """
    d = update_docket_metadata(d, iquery_data)
    try:
        d.save()
        add_bankruptcy_data_to_docket(d, iquery_data)
    except IntegrityError as exc:
        msg = "Integrity error while saving iquery response."
        if self.request.retries == self.max_retries:
            logger.warning(msg)
            return
        logger.info("%s Retrying.", msg)
        raise self.retry(exc=exc)

    add_tags_to_objs(tag_names, [d])
    if add_to_solr:
        add_items_to_solr([d.pk], "search.Docket")
    logger.info(f"Created/updated docket: {d}")
    return d.pk


def process_orphan_documents(
    rds_created: List[RECAPDocument],
    court_id: int,
    docket_date: date,
) -> None:
    """After we finish processing a docket upload add any PDFs we already had
    for that docket that were lingering in our processing queue. This addresses
    the issue that arises when somebody (somehow) uploads a PDF without first
    uploading a docket.
    """
    pacer_doc_ids = [rd.pacer_doc_id for rd in rds_created]
    if docket_date:
        # If we get a date from the docket, set the cutoff to 30 days prior for
        # good measure.
        cutoff_date = docket_date - timedelta(days=30)
    else:
        # No date from docket. Limit ourselves to the last 180 days. This will
        # help prevent items with weird errors from plaguing us forever.
        cutoff_date = now() - timedelta(days=180)
    pqs = ProcessingQueue.objects.filter(
        pacer_doc_id__in=pacer_doc_ids,
        court_id=court_id,
        status=PROCESSING_STATUS.FAILED,
        upload_type=UPLOAD_TYPE.PDF,
        debug=False,
        date_modified__gt=cutoff_date,
    ).values_list("pk", flat=True)
    for pq in pqs:
        try:
            from cl.recap.tasks import process_recap_pdf

            process_recap_pdf(pq)
        except:
            # We can ignore this. If we don't, we get all of the
            # exceptions that were previously raised for the
            # processing queue items a second time.
            pass
