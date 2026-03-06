from django.db.models import QuerySet

from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import RECAPDocument
from cl.search.utils import seal_documents


class Command(VerboseCommand):
    help = "Seal RECAPDocuments by deleting files, removing from Internet Archive, and marking as sealed."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--docket-id",
            type=int,
            required=True,
            help="The docket ID containing the documents to seal.",
        )
        parser.add_argument(
            "--entry-number",
            type=int,
            help="The docket entry number to seal. If omitted, all "
            "documents on the docket are sealed.",
        )
        parser.add_argument(
            "--rd-id",
            type=int,
            nargs="+",
            help="Specific RECAPDocument ID(s) to seal. If omitted, all "
            "documents matching the docket/entry filters are sealed.",
        )

    def handle(self, *args, **options) -> None:
        super().handle(*args, **options)

        docket_id: int = options["docket_id"]
        entry_number: int | None = options["entry_number"]
        rd_ids: list[int] | None = options["rd_id"]

        rds: QuerySet = RECAPDocument.objects.filter(
            docket_entry__docket_id=docket_id,
        )
        if entry_number is not None:
            rds = rds.filter(docket_entry__entry_number=entry_number)
        if rd_ids:
            rds = rds.filter(pk__in=rd_ids)

        count = rds.count()
        if not count:
            logger.info("No RECAPDocuments found matching the given filters.")
            return

        logger.info("Sealing %d RECAPDocument(s)...", count)
        ia_failures = seal_documents(rds)
        if ia_failures:
            logger.warning(
                "Failed to remove %d item(s) from Internet Archive:",
                len(ia_failures),
            )
            for url in ia_failures:
                logger.warning("  - %s", url)
        else:
            logger.info("Successfully sealed %d document(s).", count)
