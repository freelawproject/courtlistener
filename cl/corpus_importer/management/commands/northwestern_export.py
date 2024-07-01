from cl.corpus_importer.tasks import save_ia_docket_to_disk
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Court, Docket

BULK_OUTPUT_DIRECTORY = "/tmp/northwestern-export/"


def do_bulk_export(options):
    """Save selected dockets from 2016 to disk

    This will serialize the items to disk using celery tasks and the IA
    serializer.
    """
    q = options["queue"]
    offset = options["offset"]
    throttle = CeleryThrottle(queue_name=q)
    if offset > 0:
        logger.info("Skipping dockets with PK less than than %s", offset)
    d_pks = (
        Docket.objects.filter(
            court__jurisdiction=Court.FEDERAL_DISTRICT,
            pk__gt=offset,
            source__in=Docket.RECAP_SOURCES(),
            date_filed__gte="2016-01-01",
            date_filed__lte="2016-12-31",
        )
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    for i, d_pk in enumerate(d_pks):
        if i >= options["limit"] > 0:
            break
        logger.info("Doing item %s with pk %s", i, d_pk)
        throttle.maybe_wait()
        save_ia_docket_to_disk.apply_async(
            args=(d_pk, options["output_directory"]), queue=q
        )


class Command(VerboseCommand):
    help = "Create a big archive of dockets for a client."
    tasks = ("bulk_export",)

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="The the docket PK below which you do not want to process. "
            "(It does *not* correspond to the number of completed items.)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="After doing this number, stop. Do all of them by default.",
        )
        parser.add_argument(
            "--task",
            type=str,
            help=f"The task to perform. One of {', '.join(self.tasks)}",
            required=True,
        )
        parser.add_argument(
            "--output-directory",
            type=str,
            help="Where the bulk data will be output to. Note that if Docker "
            "is used for Celery, this is a direcotry *inside* docker.",
            default=BULK_OUTPUT_DIRECTORY,
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        if options["task"] == "bulk_export":
            do_bulk_export(options)
        else:
            raise NotImplementedError(
                "Unknown task: %s. Valid tasks are: %s"
                % (options["task"], ", ".join(self.tasks))
            )
