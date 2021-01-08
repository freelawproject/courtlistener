import json
from typing import Optional, Dict, Union

from cl.disclosures.models import FinancialDisclosure
from cl.disclosures.tasks import import_disclosure
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger


def has_been_extracted(data: Dict[str, Union[str, int, list]]) -> bool:
    """Has PDF been extracted

    Method added to skip tiff to pdf conversion if
    document has already been converted and saved but
    not yet extracted.

    :param data: File data
    :return: Whether document has been extracted
    """
    if data["disclosure_type"] == "jw" or data["disclosure_type"] == "single":
        url = data["url"]
    else:
        url = data["urls"][0]

    return FinancialDisclosure.objects.filter(
        download_filepath=url, has_been_extracted=True
    ).exists()


def import_financial_disclosures(
    filepath: str, skip_until: Optional[str], queue_name: str, min_size: int
) -> None:
    """Import financial documents into courtlistener.

    :param filepath: Path to file data to import.
    :param skip_until: ID if any to skip until.
    :param queue_name: The celery queue name
    :param min_size: The minimum items in a queue
    :return:None
    """
    throttle = CeleryThrottle(
        queue_name=queue_name,
        min_items=min_size,
    )
    with open(filepath) as f:
        disclosures = json.load(f)

    for data in disclosures:
        throttle.maybe_wait()
        if data["id"] < skip_until:
            continue

        # Check download_filepath to see if it has been processed before.
        if has_been_extracted(data):
            logger.info("Document already extracted and saved.")
            continue

        # Add disclosures to celery queue
        import_disclosure.apply_async(
            args=[data],
            queue_name=queue_name,
        )


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

        parser.add_argument(
            "--min-size",
            default=1,
            type=int,
            help="Minimum tasks in a queue (max = min x 2)",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        import_financial_disclosures(
            filepath=options["filepath"],
            skip_until=options["skip_until"],
            queue_name=options["queue"],
            min_size=options["min_size"],
        )
