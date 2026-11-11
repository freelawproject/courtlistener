from django.conf import settings

from cl.citations.models import UnmatchedCitationFromRECAPDocument
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.deletion_utils import delete_document_citations
from cl.search.models import OpinionsCitedByRECAPDocument, RECAPDocument


def get_sealed_documents_with_citations() -> list[int]:
    """Find sealed RECAPDocuments that still have citations to case law.

    Queried from the citation tables rather than from RECAPDocument so the
    database only has to return the sealed documents that actually have
    something to clean up, instead of every sealed document.

    :return: A sorted list of RECAPDocument IDs.
    """
    cited_opinions = OpinionsCitedByRECAPDocument.objects.filter(
        citing_document__is_sealed=True
    ).values_list("citing_document_id", flat=True)
    unmatched = UnmatchedCitationFromRECAPDocument.objects.filter(
        citing_recapdocument__is_sealed=True
    ).values_list("citing_recapdocument_id", flat=True)
    return sorted(set(cited_opinions) | set(unmatched))


class Command(VerboseCommand):
    help = (
        "Delete the case law citations left behind on RECAPDocuments that "
        "were sealed before sealing began removing them. Sealing scrubs a "
        "document's text, so the citations mined from that text should not "
        "outlive it."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report what would be cleaned up without changing anything.",
        )

    def handle(self, *args, **options) -> None:
        super().handle(*args, **options)

        rd_ids = get_sealed_documents_with_citations()
        if not rd_ids:
            logger.info("No sealed documents have citations. Nothing to do.")
            return

        if options["dry_run"]:
            logger.info(
                "Would clean up citations on %d sealed document(s): %s",
                len(rd_ids),
                rd_ids,
            )
            return

        logger.info(
            "Cleaning up citations on %d sealed document(s)...", len(rd_ids)
        )
        # delete_document_citations enqueues an ES update per document on the
        # ETL queue, so throttle against that queue to avoid flooding it.
        throttle = CeleryThrottle(queue_name=settings.CELERY_ETL_TASK_QUEUE)
        for i, rd in enumerate(
            RECAPDocument.objects.filter(pk__in=rd_ids).iterator(), start=1
        ):
            throttle.maybe_wait()
            delete_document_citations(rd)
            if not i % 100:
                logger.info("Processed %d/%d documents.", i, len(rd_ids))

        logger.info(
            "Cleaned up citations on %d sealed document(s).", len(rd_ids)
        )
