import json

from cl.disclosures.models import FinancialDisclosure
from cl.disclosures.tasks import import_disclosure
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger


def import_financial_disclosures(
    filepath: str,
    skip_until: int,
    queue_name: str,
) -> None:
    """Import financial documents into courtlistener.

    :param filepath: Path to file data to import.
    :param skip_until: ID if any to skip until.
    :param queue_name: The celery queue name.
    :return:None
    """
    throttle = CeleryThrottle(queue_name=queue_name)
    with open(filepath) as f:
        disclosures = json.load(f)

    for data in disclosures:
        if data["id"] < skip_until:
            continue

        # Check download_filepath to see if it has been processed before.
        if FinancialDisclosure.objects.filter(
            download_filepath=data["url"], has_been_extracted=True
        ).exists():
            logger.info(f"Document already extracted and saved: {data['id']}.")
            continue

        throttle.maybe_wait()

        # Add disclosures to celery queue
        import_disclosure.apply_async(args=[data], queue=queue_name)


class Command(VerboseCommand):
    help = "Add financial disclosures to CL database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--filepath",
            required=True,
            help="Filepath to json identify documents to process.",
        )

        parser.add_argument(
            "--skip-until",
            required=False,
            type=int,
            default=0,
            help="Skip until, uses an id to skip processes",
        )

        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        import_financial_disclosures(
            filepath=options["filepath"],
            skip_until=options["skip_until"],
            queue_name=options["queue"],
        )
