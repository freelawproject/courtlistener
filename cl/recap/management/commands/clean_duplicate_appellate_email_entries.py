import logging

from django.db import transaction

from cl.favorites.models import Prayer
from cl.favorites.utils import repoint_notes
from cl.lib.command_utils import VerboseCommand
from cl.recap.models import EmailProcessingQueue
from cl.search.models import DocketEntry, RECAPDocument

logger = logging.getLogger(__name__)


def find_duplicate_groups(docket_id: int) -> list[list[RECAPDocument]]:
    """Find duplicate RECAPDocument groups within a docket.

    A duplicate group is a set of main RECAPDocuments in
    this docket that share a pacer_doc_id but belong to different
    DocketEntry rows.

    :param docket_id: The Docket id to scan.
    :return: A list of duplicate groups, each a list of RECAPDocument
        instances (at least 2 per group).
    """
    docs = RECAPDocument.objects.filter(
        docket_entry__docket_id=docket_id,
        document_type=RECAPDocument.PACER_DOCUMENT,
    ).exclude(pacer_doc_id="")

    by_pacer_doc_id: dict[str, list[RECAPDocument]] = {}
    for doc in docs.iterator():
        by_pacer_doc_id.setdefault(doc.pacer_doc_id, []).append(doc)

    duplicate_groups = []
    for pacer_doc_id, group in by_pacer_doc_id.items():
        distinct_entry_ids = {d.docket_entry_id for d in group}
        if len(distinct_entry_ids) > 1:
            duplicate_groups.append(group)
    return duplicate_groups


def _repoint_or_delete_favorites(
    losers: list[RECAPDocument], keeper: RECAPDocument
) -> None:
    """Move each loser's Notes/Prayers to the keeper, or drop them if the
    same user already has one on the keeper.

    :param losers: The losing RECAPDocuments.
    :param keeper: The RECAPDocument being kept.
    :return: None
    """
    for loser in losers:
        repoint_notes(keeper, loser)

    loser_pks = [d.pk for d in losers]
    keeper_prayer_users = set(
        Prayer.objects.filter(recap_document_id=keeper.pk).values_list(
            "user_id", flat=True
        )
    )
    for prayer in Prayer.objects.filter(recap_document_id__in=loser_pks):
        if prayer.user_id in keeper_prayer_users:
            prayer.delete()
        else:
            prayer.recap_document_id = keeper.pk
            prayer.save(update_fields=["recap_document"])
            keeper_prayer_users.add(prayer.user_id)


def _pick_keeper(
    duplicate_group: list[RECAPDocument],
) -> RECAPDocument:
    """Pick which copy in a duplicate group survives.

    Exactly one copy having a PDF is the strongest signal and wins outright.
    Otherwise, it choose the most recently modified copy among those
    with a non-null ocr_status, falling back to the most recently
    modified copy overall if every candidate's ocr_status is null.

    :param duplicate_group: The RECAPDocuments sharing a pacer_doc_id.
    :return: The RECAPDocument to keep.
    """
    with_pdf = [d for d in duplicate_group if d.filepath_local]
    candidates = with_pdf if with_pdf else duplicate_group

    with_ocr = [d for d in candidates if d.ocr_status is not None]
    candidates = with_ocr if with_ocr else candidates
    return max(candidates, key=lambda d: d.date_modified)


def process_duplicate_group(
    pacer_doc_id: str, duplicate_group: list[RECAPDocument], clean: bool
) -> None:
    """Resolve one duplicate group: keep one copy, drop the rest.

    Groups that fail a safety check are logged and skipped entirely
    rather than partially processed, they need a manual review.

    :param pacer_doc_id: The shared pacer_doc_id for this group, used only
        for logging.
    :param duplicate_group: The RECAPDocuments sharing that pacer_doc_id,
        spread across more than one DocketEntry.
    :param clean: Whether to actually perform the writes, or only log the
        plan.
    """
    keeper = _pick_keeper(duplicate_group)
    losers = [d for d in duplicate_group if d.pk != keeper.pk]
    loser_entry_ids = {d.docket_entry_id for d in losers}

    if keeper.docket_entry_id in loser_entry_ids:
        # Defensive: an already-anomalous data shape (e.g. two group
        # documents sharing both docket_entry_id and pacer_doc_id). Never
        # delete the entry we just chose to keep.
        logger.error(
            "Duplicate group pacer_doc_id=%s: keeper RECAPDocument %s's "
            "own docket_entry %s is also in the loser set - this "
            "indicates an unexpected data shape. Skipping for manual "
            "review.",
            pacer_doc_id,
            keeper.pk,
            keeper.docket_entry_id,
        )
        return

    loser_pks = [d.pk for d in losers]

    extra_docs_count = (
        RECAPDocument.objects.filter(docket_entry_id__in=loser_entry_ids)
        .exclude(pk__in=loser_pks)
        .count()
    )
    if extra_docs_count:
        warning = (
            f"losing DocketEntry(s) {sorted(loser_entry_ids)} also contain "
            f"{extra_docs_count} document(s) that aren't part of this "
            "duplicate group (attachments or unrelated main documents) - "
            "skipping for manual review instead of destroying them."
        )
        logger.warning(
            "Duplicate group pacer_doc_id=%s: %s", pacer_doc_id, warning
        )
        return

    if not (len(pacer_doc_id) >= 9 and pacer_doc_id.isdigit()):
        logger.warning(
            "Duplicate group pacer_doc_id=%s: not a long numeric "
            "appellate pacer_doc_id - skipping for manual review.",
            pacer_doc_id,
        )
        return
    new_document_number = str(int(f"{pacer_doc_id[:3]}0{pacer_doc_id[4:]}"))

    docket_id = keeper.docket_entry.docket_id
    entry_number_collision = (
        DocketEntry.objects.filter(
            docket_id=docket_id, entry_number=int(new_document_number)
        )
        .exclude(pk=keeper.docket_entry_id)
        .exclude(pk__in=loser_entry_ids)
        .exists()
    )
    if entry_number_collision:
        logger.warning(
            "Duplicate group pacer_doc_id=%s: recomputed entry_number %s "
            "already exists on another DocketEntry in docket %s -- "
            "skipping for manual review instead of creating a collision.",
            pacer_doc_id,
            new_document_number,
            docket_id,
        )
        return

    logger.info(
        "Duplicate group pacer_doc_id=%s: keeping RECAPDocument %s "
        "(docket_entry %s), deleting DocketEntry(s) %s. "
        "document_number/entry_number -> %s.",
        pacer_doc_id,
        keeper.pk,
        keeper.docket_entry_id,
        sorted(loser_entry_ids),
        new_document_number,
    )

    if not clean:
        return

    try:
        with transaction.atomic():
            # Lock + re-check immediately before writing.
            list(
                DocketEntry.objects.select_for_update().filter(
                    pk__in=loser_entry_ids
                )
            )
            extra_docs_count = (
                RECAPDocument.objects.filter(
                    docket_entry_id__in=loser_entry_ids
                )
                .exclude(pk__in=loser_pks)
                .count()
            )
            if extra_docs_count:
                recheck_warning = (
                    f"losing DocketEntry(s) {sorted(loser_entry_ids)} also contain "
                    f"{extra_docs_count} document(s) that aren't part of this "
                    "duplicate group (attachments or unrelated main documents) - "
                    "skipping for manual review instead of destroying them."
                )
                logger.warning(
                    "Duplicate group pacer_doc_id=%s: %s.",
                    pacer_doc_id,
                    recheck_warning,
                )
                return

            _repoint_or_delete_favorites(losers, keeper)
            DocketEntry.objects.filter(pk__in=loser_entry_ids).delete()
            keeper.document_number = new_document_number
            keeper.save(update_fields=["document_number"])
            keeper.docket_entry.entry_number = int(new_document_number)
            keeper.docket_entry.save(update_fields=["entry_number"])
    except Exception:
        logger.exception(
            "Duplicate group pacer_doc_id=%s: an error occurred inside or "
            "immediately after the write transaction.",
            pacer_doc_id,
        )
        return


def clean_duplicate_appellate_email_entries(
    courts: list[str], clean: bool
) -> None:
    """Clean up duplicate docket entries: recap.email and
    extension ingestion used to derive different document_number/
    entry_number values for the same PACER document, creating two
    DocketEntry/RECAPDocument pairs where there should be one.
    #7079 fixed the derivation going forward; this cleans
    up the historical duplicates.

    :param courts: Court ids to search for candidate dockets.
    :param clean: Whether to actually perform the writes, or only log the
        plan.
    :return: None
    """
    docket_ids = (
        EmailProcessingQueue.objects.filter(court_id__in=courts)
        .filter(recap_documents__isnull=False)
        .values_list("recap_documents__docket_entry__docket_id", flat=True)
        .distinct()
    )
    logger.info(
        "Found %d candidate docket(s) in %s with email-sourced documents. "
        "clean=%s.",
        docket_ids.count(),
        courts,
        clean,
    )

    total_duplicate_groups = 0
    for docket_id in docket_ids.iterator():
        for duplicate_group in find_duplicate_groups(docket_id):
            total_duplicate_groups += 1
            pacer_doc_id = duplicate_group[0].pacer_doc_id
            try:
                process_duplicate_group(pacer_doc_id, duplicate_group, clean)
            except Exception:
                logger.exception(
                    "Unhandled error processing duplicate group "
                    "pacer_doc_id=%s in docket %s - skipping this group "
                    "and continuing with the rest of the run.",
                    pacer_doc_id,
                    docket_id,
                )

    logger.info("Done. %d duplicate group(s) found.", total_duplicate_groups)


class Command(VerboseCommand):
    help = (
        "Clean up duplicated docket entries in appellate courts without "
        "regular document numbers."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--courts",
            required=True,
            nargs="+",
            help="Court ids to search for duplicate entries, e.g. ca8 cadc.",
        )
        parser.add_argument(
            "--clean",
            action="store_true",
            default=False,
            help="Actually perform the cleanup. Without this flag, only "
            "logs the plan.",
        )

    def handle(self, *args, **options):
        clean_duplicate_appellate_email_entries(
            options["courts"], options["clean"]
        )
