from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db.models import QuerySet
from django.forms.models import model_to_dict
from django.template import loader

from cl.recap.models import UPLOAD_TYPE, PacerFetchQueue, ProcessingQueue
from cl.search.models import Docket, DocketEntry, RECAPDocument


def sort_acms_docket_entries(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Sort ACMs docket entries to ensure consistent and predictable ordering.

    If all entries have a 'document_number', the list is sorted solely by that
    field. Otherwise, entries are sorted primarily by 'date_filed', then by the
    presence of a 'document_number' (placing entries without one last for each
    date), and finally by 'document_number'.

    This approach mirrors the typical ordering found in docket reports.
    """
    if all([d["document_number"] for d in entries]):
        return sorted(entries, key=lambda d: d["document_number"])
    return sorted(
        entries,
        key=lambda d: (
            d["date_filed"],
            d["document_number"] is None,
            d["document_number"],
        ),
    )


def get_court_id_from_fetch_queue(fq: PacerFetchQueue | dict[str, Any]) -> str:
    """Extracts the court ID from a PacerFetchQueue object or a dictionary.

    This function attempts to retrieve the court ID from the provided
    PacerFetchQueue object or dictionary. It checks for the court ID in
    the following order:

    1. From the recap_document's docket_entry's docket.
    2. From the docket object.
    3. The top-level `court_id` (for PacerFetchQueue objects) or `court.pk`
       (for dictionaries).

    :param fq: A PacerFetchQueue object or a dictionary representing a
    PacerFetchQueue.
    :return: The court ID as a string.
    """

    # Convert PacerFetchQueue to dictionary if necessary.  This allows us to
    # handle both types consistently.
    attrs = model_to_dict(fq) if isinstance(fq, PacerFetchQueue) else fq
    if attrs.get("recap_document"):
        rd_id = (
            fq.recap_document_id
            if isinstance(fq, PacerFetchQueue)
            else attrs["recap_document"].pk
        )
        docket = (
            Docket.objects.filter(docket_entries__recap_documents__id=rd_id)
            .only("court_id")
            .first()
        )
        court_id = docket.court_id
    elif attrs.get("docket"):
        court_id = (
            fq.docket.court_id
            if isinstance(fq, PacerFetchQueue)
            else attrs["docket"].court_id
        )
    else:
        court_id = (
            fq.court_id
            if isinstance(fq, PacerFetchQueue)
            else attrs["court"].pk
        )

    return court_id


def get_main_rds(court_id: str, pacer_doc_id: str) -> QuerySet:
    """
    Return the main RECAPDocument queryset for a given court and pacer_doc_id.
    :param court_id: The court ID to query.
    :param pacer_doc_id: The pacer document ID.
    :return: The main RECAPDocument queryset.
    """
    main_rds_qs = (
        RECAPDocument.objects.select_related("docket_entry__docket")
        .filter(
            pacer_doc_id=pacer_doc_id,
            docket_entry__docket__court_id=court_id,
        )
        .order_by("docket_entry__docket__pacer_case_id")
        .distinct("docket_entry__docket__pacer_case_id")
        .only(
            "pacer_doc_id",
            "docket_entry__docket__pacer_case_id",
            "docket_entry__docket__court_id",
        )
    )
    return main_rds_qs


def find_available_sibling_rd(rd: RECAPDocument) -> RECAPDocument | None:
    """Return a sibling RECAPDocument that already holds the PDF for this row.

    PACER assigns separate `pacer_case_id`s to the master docket and each
    sub-docket of a criminal case (the "doppelganger" problem tracked in
    issue #2185). PDFs are stored under whichever `pacer_case_id` was
    active at upload time, so `RECAPDocument` rows on the sibling dockets
    show `is_available=False` even though the bytes are already in the
    bucket — until backward replication (#4864) lands and copies the file
    to each sibling's own path.

    A sibling here is a `RECAPDocument` in the same court with the same
    `pacer_doc_id` and `attachment_number` but a different `pacer_case_id`
    on its docket. Rows marked `is_sealed=True` are excluded because
    sealing on PACER signals the file should not be served, regardless of
    where the bytes happen to sit.

    :param rd: The RECAPDocument whose own PDF is unavailable.
    :return: The first available, unsealed sibling, or None if none exists.
    """
    if not rd.pacer_doc_id:
        return None

    sibling = (
        RECAPDocument.objects.select_related("docket_entry__docket")
        .filter(
            pacer_doc_id=rd.pacer_doc_id,
            attachment_number=rd.attachment_number,
            docket_entry__docket__court_id=rd.docket_entry.docket.court_id,
            is_available=True,
        )
        .exclude(is_sealed=True)
        .exclude(filepath_local="")
        .exclude(
            docket_entry__docket__pacer_case_id=rd.docket_entry.docket.pacer_case_id
        )
        .order_by("docket_entry__docket__pacer_case_id", "pk")
        .first()
    )
    return sibling


def find_available_sibling_rd_map(
    rds: Iterable[RECAPDocument],
) -> dict[int, RECAPDocument]:
    """Bulk version of :func:`find_available_sibling_rd` for serialization.

    Collapses the per-row sibling lookup into a single query so list/nested
    API responses don't fan out to one query per stranded RECAPDocument.

    Inputs that already hold their own PDF (or have a blank `pacer_doc_id`)
    are skipped — they don't need a sibling. The remaining rows are pooled
    by `pacer_doc_id`, a single query fetches every available, unsealed
    candidate matching any of those `pacer_doc_id`s, and candidates are
    matched back to inputs by `(court_id, pacer_doc_id, attachment_number)`
    with the candidate's `pacer_case_id` required to differ from the input's.

    When multiple siblings qualify for the same input, the one with the
    lowest `(pacer_case_id, pk)` wins — same ordering as the single-row
    helper, so the two are consistent.

    Each input must have `docket_entry__docket` accessible without an
    extra query. The DRF viewsets that use the serializer already
    `select_related` that path.

    :param rds: The RECAPDocument rows about to be serialized.
    :return: ``{rd.pk: sibling_rd}`` for inputs where a sibling was found.
    """
    rds_needing_sibling: list[RECAPDocument] = []
    pacer_doc_ids: set[str] = set()
    for rd in rds:
        if not rd.pacer_doc_id:
            continue
        if rd.is_available and rd.filepath_local:
            continue
        rds_needing_sibling.append(rd)
        pacer_doc_ids.add(rd.pacer_doc_id)

    if not rds_needing_sibling:
        return {}

    candidates = (
        RECAPDocument.objects.select_related("docket_entry__docket")
        .filter(
            pacer_doc_id__in=pacer_doc_ids,
            is_available=True,
        )
        .exclude(is_sealed=True)
        .exclude(filepath_local="")
        .order_by("docket_entry__docket__pacer_case_id", "pk")
    )

    candidates_by_key: dict[
        tuple[str, str, int | None], list[RECAPDocument]
    ] = defaultdict(list)
    for cand in candidates:
        key = (
            cand.docket_entry.docket.court_id,
            cand.pacer_doc_id,
            cand.attachment_number,
        )
        candidates_by_key[key].append(cand)

    result: dict[int, RECAPDocument] = {}
    for rd in rds_needing_sibling:
        docket = rd.docket_entry.docket
        key = (docket.court_id, rd.pacer_doc_id, rd.attachment_number)
        for cand in candidates_by_key.get(key, ()):
            if cand.docket_entry.docket.pacer_case_id != docket.pacer_case_id:
                result[rd.pk] = cand
                break

    return result


def find_subdocket_pdf_rds_from_data(
    user_id: int,
    court_id: str,
    pacer_doc_id: str,
    pacer_case_ids: list[str],
    pdf_bytes: bytes,
) -> list[int]:
    """Look for RECAP Documents that belong to subdockets and create
     ProcessingQueue instances to handle the PDF replication.

    :param user_id: The User ID.
    :param court_id: The Court ID.
    :param pacer_doc_id: The PACER document ID to look for subdockets.
    :param pacer_case_ids: A list of PACER case IDs to exclude from the lookup.
    :param pdf_bytes: The raw PDF bytes for the document to be replicated.
    :return: A list of ProcessingQueue PKs.
    """

    sub_docket_main_rds = list(
        get_main_rds(court_id, pacer_doc_id)
        .exclude(docket_entry__docket__pacer_case_id__in=pacer_case_ids)
        .exclude(is_available=True)
    )
    sub_docket_pqs = []
    for main_rd in sub_docket_main_rds:
        # Create PQs related to RD that require replication.
        sub_docket_pqs.append(
            ProcessingQueue(
                uploader_id=user_id,
                pacer_doc_id=main_rd.pacer_doc_id,
                pacer_case_id=main_rd.docket_entry.docket.pacer_case_id,
                document_number=main_rd.document_number,
                attachment_number=main_rd.attachment_number,
                court_id=court_id,
                upload_type=UPLOAD_TYPE.PDF,
                filepath_local=ContentFile(pdf_bytes, name="document.pdf"),
            )
        )

    if not sub_docket_pqs:
        return []

    return [
        pq.pk for pq in ProcessingQueue.objects.bulk_create(sub_docket_pqs)
    ]


def find_subdocket_atts_rds_from_data(
    user_id: int,
    court_id: str,
    pacer_doc_id: str,
    pacer_case_ids: list[str],
    att_bytes: bytes,
) -> list[tuple[int, bool]]:
    """Look for RECAP Documents that belong to subdockets and create
     ProcessingQueue instances to handle the Attachment page replication.

    :param user_id: The User ID.
    :param court_id: The Court ID.
    :param pacer_doc_id: The PACER document ID to look for subdockets.
    :param pacer_case_ids: A list of PACER case IDs to exclude from the lookup.
    :param att_bytes: The attachment page bytes for the document to be replicated.
    :return: A two-tuple containing a list of ProcessingQueue pks to process,
    and a boolean indicating whether the PQ belongs to subdocket replication.
    """
    # Logic to replicate the PDF sub-dockets matched by RECAPDocument
    sub_docket_main_rds = list(
        get_main_rds(court_id, pacer_doc_id).exclude(
            docket_entry__docket__pacer_case_id__in=pacer_case_ids
        )
    )

    sub_docket_pqs = []
    for main_rd in sub_docket_main_rds:
        # Create PQs related to RD that require replication.
        sub_docket_pqs.append(
            ProcessingQueue(
                uploader_id=user_id,
                pacer_doc_id=main_rd.pacer_doc_id,
                pacer_case_id=main_rd.docket_entry.docket.pacer_case_id,
                court_id=court_id,
                upload_type=UPLOAD_TYPE.ATTACHMENT_PAGE,
                filepath_local=ContentFile(
                    att_bytes, name="attachment_page.html"
                ),
            )
        )

    if not sub_docket_pqs:
        return []

    subdocket_replication = True
    return [
        (pq.pk, subdocket_replication)
        for pq in ProcessingQueue.objects.bulk_create(sub_docket_pqs)
    ]


def send_bad_redaction_email(
    rd: RECAPDocument,
    redactions: dict,
) -> None:
    """Send email alert when bad redactions are detected.

    :param rd: The RECAPDocument with bad redactions
    :param redactions: Dict of page_num -> list of {text, bbox}
    """
    template = loader.get_template("emails/bad_redaction_alert.txt")

    de = DocketEntry.objects.select_related("docket__court").get(
        pk=rd.docket_entry_id
    )
    docket = de.docket
    court = docket.court

    context = {
        "rd_id": rd.pk,
        "docket_name": docket.case_name,
        "court": court.full_name,
        "document_number": rd.document_number,
        "redactions": redactions,
        "document_url": f"https://www.courtlistener.com{rd.get_absolute_url()}",
    }

    send_mail(
        subject=f"Bad Redactions Detected: {docket.case_name[:50]}",
        message=template.render(context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.BAD_REDACTION_EMAIL],  # type: ignore[misc]
    )
