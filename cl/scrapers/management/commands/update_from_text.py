import traceback
from datetime import datetime

from django.db import transaction

from cl.lib.command_utils import ScraperCommand, logger
from cl.scrapers.tasks import extract_doc_content, update_document_from_text
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SOURCES,
    Opinion,
    OpinionCluster,
)


def rerun_extract_from_text(
    opinion: Opinion, juriscraper_module: str, stats: dict[str, int]
):
    """
    Reruns `update_document_from_text` from the scraper flow, saving changes

    `update_document_from_text` calls `Site.extract_from_text` and assigns
    any changes to the proper objets, in place, but they are not saved.
    This method saves the ones with actual changes

    :param opinion: the Opinion on which to apply extract_from_text
    :param juriscraper_module: the scraper module path
    :param stats: dict to accumulate counts for reporting. Modified in place

    :return None
    """
    if not opinion.plain_text and not opinion.html:
        # May be an opinion entirely from a merged corpus
        # or an error during text extraction
        logger.info(
            "Opinion %s has no `plain_text` or `html`"
            "to extract from. Executing extraction",
            opinion.id,
        )
        stats["No text to extract from"] += 1
        extract_doc_content(
            pk=opinion.pk,
            ocr_available=True,
            citation_jitter=True,
            juriscraper_module=juriscraper_module,
        )
        return

    with transaction.atomic():
        try:
            changes = update_document_from_text(opinion, juriscraper_module)
        except:
            # Probably a bad implementation of `extract_from_text`
            logger.debug(
                "`update_document_from_text` failed for opinion %s. Traceback: %s",
                opinion.id,
                traceback.format_exc(),
            )
            stats["Error"] += 1
            return

        if not changes:
            logger.info("Did not get any metadata for opinion %s", opinion.id)
            stats["No metadata extracted"] += 1
            return

        logger.info("Processing opinion %s", opinion.id)

        # Check if changes exist before saving, to prevent unnecessary DB queries
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

        if changes.get("citation_created"):
            logger.info("Citation created with data %s", changes["Citation"])
            stats["Citation"] += 1
        elif changes.get("Citation"):
            logger.debug("Citation not created. Data %s", changes["Citation"])


class Command(ScraperCommand):
    help = """Updates objects by running Site.extract_from_text
    over extracted content found on Opinion.plain_text or Opinion.html.

    If `--opinion-ids` is used, filters will be ignored.
    If not, the 2 date filters will be required, to prevent triggering
    unwanted reprocessing of the whole court's dataset

    Recommended use is to run over a sample of the target time period
    and check if updates over Docket, OpinionCluster, Opinion and
    Citation are as expected
    """
    # For aggregate reporting at the end of the command
    stats = {
        "Docket": 0,
        "OpinionCluster": 0,
        "Opinion": 0,
        "Citation": 0,
        "No text to extract from": 0,
        "No metadata extracted": 0,
        "Error": 0,
    }
    juriscraper_module_type = "opinions"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--opinion-ids",
            nargs="+",
            type=int,
            help="""The Opinion ids to re-process.
            May be more than one. If this argument is used,
            other filters will be ignored""",
        )
        parser.add_argument(
            "--date-filed-gte",
            default="",
            type=self.parse_input_date,
            help=r"""A filter value in %Y-%m-%d or %Y/%m/%d format.
            OpinionCluster.date_filed will have to be greater or equal""",
        )
        parser.add_argument(
            "--date-filed-lte",
            default="",
            type=self.parse_input_date,
            help=r"""A filter value in %Y-%m-%d or %Y/%m/%d format.
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
        juriscraper_module = options["court_id"]

        if options["opinion_ids"]:
            opinions = Opinion.objects.filter(id__in=options["opinion_ids"])
            for op in opinions:
                rerun_extract_from_text(op, juriscraper_module, self.stats)

            logger.info("Modified objects counts: %s", self.stats)
            return

        if not (options["date_filed_gte"] and options["date_filed_lte"]):
            raise ValueError(
                "Both `date-filed-gte` and `date-filed-lte` arguments should have values"
            )

        court_id = juriscraper_module.split(".")[-1].split("_")[0]
        query = {
            "docket__court_id": court_id,
            "date_filed__gte": options["date_filed_gte"],
            "date_filed__lte": options["date_filed_lte"],
            "source__contains": SOURCES.COURT_WEBSITE,
        }

        if options["cluster_status"]:
            query["precedential_status"] = options["cluster_status"]

        qs = OpinionCluster.objects.filter(**query).prefetch_related(
            "sub_opinions"
        )
        logger.debug("Found %s objects matching query %s", qs.count(), query)

        for cluster in qs:
            opinions = cluster.sub_opinions.all()
            for op in opinions:
                rerun_extract_from_text(op, juriscraper_module, self.stats)

        logger.info("Modified objects counts: %s", self.stats)

    def parse_input_date(self, date_string: str) -> datetime | str:
        """Parses a date string in accepted formats

        :param date_string: the date string in "%Y/%m/%d" or "%Y-%m-%d"
        :return: an empty string if the input was empty; or the date object
        """
        parsed_date = ""
        if "/" in date_string:
            parsed_date = datetime.strptime(date_string, "%Y/%m/%d")
        elif "-" in date_string:
            parsed_date = datetime.strptime(date_string, "%Y-%m-%d")
        return parsed_date
