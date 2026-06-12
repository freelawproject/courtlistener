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
        ).select_related("docket_entry__docket")
        if entry_number is not None:
            rds = rds.filter(docket_entry__entry_number=entry_number)
        if rd_ids:
            rds = rds.filter(pk__in=rd_ids)

        rd_list = list(rds)
        if not rd_list:
            logger.info("No RECAPDocuments found matching the given filters.")
            return

        docket = rd_list[0].docket_entry.docket
        self.stdout.write(f"\nDocket: {docket} (ID: {docket.pk})")
        self.stdout.write(f"Court:  {docket.court_id}")
        self.stdout.write(f"\nDocuments to seal ({len(rd_list)}):")
        self.stdout.write(
            f"{'ID':>10}  {'Entry':>6}  {'Type':>12}  {'Description'}"
        )
        self.stdout.write(
            f"{'--':>10}  {'-----':>6}  {'----':>12}  {'-----------'}"
        )
        for rd in rd_list:
            de = rd.docket_entry
            desc = rd.description or de.description or ""
            if len(desc) > 60:
                desc = desc[:57] + "..."
            self.stdout.write(
                f"{rd.pk:>10}  {de.entry_number or '':>6}  "
                f"{rd.get_document_type_display():>12}  {desc}"
            )

        self.stdout.write("")
        confirm = input("Proceed with sealing? [y/N] ")
        if confirm.lower() != "y":
            self.stdout.write("Aborted.")
            return

        logger.info("Sealing %d RECAPDocument(s)...", len(rd_list))
        ia_failures = seal_documents(rds)
        if ia_failures:
            logger.warning(
                "Failed to remove %d item(s) from Internet Archive:",
                len(ia_failures),
            )
            for url in ia_failures:
                logger.warning("  - %s", url)
        else:
            logger.info("Successfully sealed %d document(s).", len(rd_list))
