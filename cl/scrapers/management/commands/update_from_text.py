from datetime import datetime

from django.db import transaction

from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.tasks import update_document_from_text
from cl.search.models import PRECEDENTIAL_STATUS, Opinion, OpinionCluster


def update_from_text(
    opinion: Opinion, juriscraper_module: str, stats: dict[str, int]
):
    """Calls `update_document_from_text` as used in the scraper flow
    and calls the corresponding model's .save()

    :param opinion: the Opinion on which to apply extract_from_text
    :param juriscraper_module: the scraper module path
    :param stats: dict to accumulate counts for reporting. Modified in place

    :return None
    """
    with transaction.atomic():
        changes = update_document_from_text(opinion, juriscraper_module)
        if not changes:
            logger.info("Did not get any metadata for opinion %s", opinion.id)
            return

        logger.info("Processing opinion %s", opinion.id)

        # Check if changes exist before saving, to prevent unecessary DB queries
        if changes.get("Docket"):
            opinion.cluster.docket.save()
            logger.debug(
                "Docket %s updated with data %s",
                opinion.cluster.docket.id,
                changes["Docket"],
            )
            stats["Docket"] += 1

        if changes.get("OpinionCluster"):
            opinion.cluster.save()
            logger.debug(
                "OpinionCluster %s updated with data %s",
                opinion.cluster.id,
                changes["OpinionCluster"],
            )
            stats["OpinionCluster"] += 1

        if changes.get("Opinion"):
            opinion.save()
            logger.debug("Opinion updated with data %s", changes["Opinion"])
            stats["Opinion"] += 1

        if changes.get("Citation"):
            if changes["Citation"].get("citation_created"):
                logger.info(
                    "Citation created with data %s", changes["Citation"]
                )
                stats["Citation"] += 1
            else:
                logger.debug(
                    "Citation not created. Data %s", changes["Citation"]
                )


class Command(VerboseCommand):
    help = """Updates objects by running Site.extract_from_text
    over extracted content found on Opinion.plain_text or Opinion.html.

    If `--opinion-ids` is used, filters will be ignored.
    If not, the 2 date filters will be required, to prevent triggering
    unwanted reprocessing of the whole court's dataset

    Recommended use is to run over a sample of the target time period
    and check if updates over Docket, OpinionCluster, Opinion and
    Citation are as expected
    """
    stats = {}  # assigned at the end of a command run, for testing

    def add_arguments(self, parser):
        parser.add_argument(
            "--juriscraper-module",
            help="""The Juriscraper file which contains the
            `extract_from_text` method to be used. The `court_id`
            will be deduced from this. Example:
            juriscraper.opinions.united_states.federal_appellate.ca1
            """,
            required=True,
        )
        parser.add_argument(
            "--opinion-ids",
            nargs="+",
            type=int,
            help="""The Opinion ids to re-process.
            May be more than one. If this argument is used,
            other filters will be ignored""",
        )
        parser.add_argument(
            "date-filed-gte",
            default="",
            help=r"""A filter value in %Y/%m/%d format.
            OpinionCluster.date_filed will have to be greater or equal""",
        )
        parser.add_argument(
            "date-filed-lte",
            default="",
            help=r"""A filter value in %Y/%m/%d format.
            OpinionCluster.date_filed will have to be less or equal""",
        )
        parser.add_argument(
            "--cluster-status",
            default="",
            choices=[value for value, name in PRECEDENTIAL_STATUS.NAMES],
            help="""A value of OpinionCluster.precedential_status. To be
            used for filtering the Opinions to be processed
            """,
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        juriscraper_module = options["juriscraper_module"]
        # For aggregate reporting
        stats = {"Docket": 0, "OpinionCluster": 0, "Opinion": 0, "Citation": 0}

        if options["opinion_ids"]:
            opinions = Opinion.objects.filter(id__in=options["opinion_ids"])
            for op in opinions:
                update_from_text(op, juriscraper_module, stats)

            logger.info("Modified objects counts: %s", stats)
            return

        if not (options["date_filed_gte"] and options["date_filed_lte"]):
            raise ValueError(
                "Both `date-filed-gte` and `date-filed-lte` arguments should have values"
            )

        court_id = juriscraper_module.split(".")[-1].split("_")[0]
        gte_date = datetime.strptime(options["date_filed_gte"], "%Y/%m/%d")
        lte_date = datetime.strptime(options["date_filed_lte"], "%Y/%m/%d")
        query = {
            "docket__court_id": court_id,
            "date_filed__gte": gte_date,
            "date_filed__lte": lte_date,
        }

        if options["cluster_status"]:
            query["precedential_status"] = options["cluster_status"]

        qs = OpinionCluster.objects.filter(**query).prefetch_related(
            "sub_opinions"
        )
        for cluster in qs:
            opinions = cluster.sub_opinions.all()
            for op in opinions:
                update_from_text(op, juriscraper_module, stats)

        logger.info("Modified objects counts: %s", stats)
        self.stats = stats
