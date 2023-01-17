import random
import re
from datetime import datetime, timedelta
from typing import Set

import pytz
import requests
from django.conf import settings
from requests import RequestException
from simplejson import JSONDecodeError

from cl.alerts.models import DocketAlert
from cl.favorites.models import DocketTag, Note
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.tasks import update_docket_info_iquery
from cl.search.models import Court, Docket


def get_docket_ids_missing_info(num_to_get: int) -> Set[int]:
    return set(
        Docket.objects.filter(
            date_filed__isnull=True,
            source__in=Docket.RECAP_SOURCES,
            court__jurisdiction__in=[
                Court.FEDERAL_DISTRICT,
                Court.FEDERAL_BANKRUPTCY,
            ],
        )
        .exclude(pacer_case_id=None)
        .order_by("-view_count")[:num_to_get]
        .values_list("pk", flat=True)
    )


def get_docket_ids() -> Set[int]:
    """Get docket IDs to update via iquery

    :return: docket IDs for which we should crawl iquery
    """
    docket_ids = set()
    if hasattr(settings, "PLAUSIBLE_API_TOKEN"):
        try:
            # Get the top 250 entry pages from the day
            #
            # curl 'https://plausible.io/api/v1/stats/breakdown?\
            #     site_id=courtlistener.com&\
            #     period=day&\
            #     date=2022-03-14&\
            #     property=visit:entry_page&\
            #     metrics=visitors&\
            #     limit=250' \
            #   -H "Authorization: Bearer XXX" | jq
            #
            # This is meant to be run early in the morning. Each site in
            # Plausible has a timezone setting. For CL, it's US/Pacific, so
            # take today's date (early in the morning Pacific time), subtract
            # one day, and that's your day for this.
            yesterday = (
                (datetime.now(pytz.timezone("US/Pacific")) - timedelta(days=1))
                .date()
                .isoformat()
            )
            r = requests.get(
                settings.PLAUSIBLE_API_URL,
                timeout=10,
                params={
                    "site_id": "courtlistener.com",
                    "period": "day",
                    "date": yesterday,
                    "property": "visit:entry_page",
                    "metrics": "visitors",
                    "limit": "250",
                },
                headers={
                    "Authorization": f"Bearer {settings.PLAUSIBLE_API_TOKEN}",
                },
            )
            r.raise_for_status()
            j = r.json()
        except (
            ConnectionRefusedError,
            JSONDecodeError,
            RequestException,
        ) as e:
            logger.warning(
                "iQuery scraper was unable to get results from Plausible. Got "
                "exception: %s" % e
            )
        else:
            # Filter to docket pages with some amount of traffic
            for item in j["results"]:
                # j["results"] is a list of dicts that look like:
                # {"entry_page": "/recap", "visitors": 68}
                # Note that Plausible's visitor count is divided by ten on
                # CourtListener to save money. The value below is thus 10× what
                # it appears to be.
                if item["visitors"] < 3:
                    continue

                url = item["entry_page"]
                if match := re.search(r"^/docket/([0-9]+)/", url):
                    docket_ids.add(match.group(1))

    # Add in docket IDs that have docket alerts, tags, or are in notes
    docket_ids.update(DocketAlert.objects.values_list("docket", flat=True))
    docket_ids.update(
        Note.objects.exclude(docket_id=None)
        .distinct("docket_id")
        .values_list("docket_id", flat=True)
    )
    docket_ids.update(
        DocketTag.objects.distinct("docket_id").values_list(
            "docket_id", flat=True
        )
    )
    docket_ids.update(
        Docket.objects.filter(
            case_name__isnull=True,
            source__in=Docket.RECAP_SOURCES,
            court__jurisdiction__in=[
                Court.FEDERAL_DISTRICT,
                Court.FEDERAL_BANKRUPTCY,
            ],
        )
        .exclude(pacer_case_id=None)
        .values_list("pk", flat=True)
    )
    return docket_ids


class Command(VerboseCommand):
    help = "Scrape PACER iquery report"

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--include-old-terminated",
            action="store_true",
            default=False,
            help="Whether to scrape dockets terminated and with no new "
            "filings in 90 days",
        )
        parser.add_argument(
            "--do-missing-date-filed",
            default=0,
            help="Whether to scrape dockets with missing date_filed field."
            "if set, should be the number of dockets to scrape",
            type=int,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        do_missing_date_filed = options["do_missing_date_filed"]
        if do_missing_date_filed:
            docket_ids = get_docket_ids_missing_info(do_missing_date_filed)
        else:
            docket_ids = get_docket_ids()
        # docket_ids = get_docket_ids().union(get_docket_ids_missing_info(100000)) #once initial scrape filling in date_filed is done, uncomment this to do these nightly
        logger.info(
            "iQuery crawling starting up. Will crawl %s dockets",
            len(docket_ids),
        )
        # Shuffle the dockets to make sure we don't hit one district all at
        # once.
        random.shuffle(list(docket_ids))
        queue = options["queue"]
        throttle = CeleryThrottle(queue_name=queue)
        now = datetime.now().date()
        include_old_terminated = options["include_old_terminated"]
        for i, docket_id in enumerate(docket_ids):
            throttle.maybe_wait()

            if i % 500 == 0:
                logger.info("Sent %s items to celery for crawling so far.", i)

            d = Docket.objects.filter(pk=docket_id).select_related("court")[0]
            too_many_days_old = 90
            terminated_too_long_ago = (
                d.date_terminated
                and (now - d.date_terminated).days > too_many_days_old
            )
            last_filing_too_long_ago = (
                d.date_last_filing
                and (now - d.date_last_filing).days > too_many_days_old
            )
            if all(
                [
                    not include_old_terminated,
                    terminated_too_long_ago,
                    last_filing_too_long_ago,
                    d.date_filed,
                    d.case_name,
                ]
            ):
                # Skip old terminated cases, but do them if we're missing
                # date_filed or case_name
                continue

            if not d.pacer_case_id:
                # No case ID, can't crawl it. Skip.
                continue

            if d.court.jurisdiction not in [
                Court.FEDERAL_DISTRICT,
                Court.FEDERAL_BANKRUPTCY,
            ]:
                # Appeals or other kind of court that got swept up. Punt.
                continue

            update_docket_info_iquery.apply_async(
                args=(d.pk, d.court_id), queue=queue
            )

        logger.info("Done!")
