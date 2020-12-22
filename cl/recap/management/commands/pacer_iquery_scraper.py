import re
from datetime import datetime
from typing import Set

import requests
from django.conf import settings
from requests import RequestException
from simplejson import JSONDecodeError

from cl.alerts.models import DocketAlert
from cl.favorites.models import Favorite
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.tasks import update_docket_info_iquery
from cl.search.models import Docket, Court


def get_docket_ids_missing_info(num_to_get: int) -> Set[int]:
    return set(
        Docket.objects.filter(
            date_filed__isnull=True, source__in=Docket.RECAP_SOURCES
        )
        .order_by("-view_count")[:num_to_get]
        .values_list("pk", flat=True)
    )


def get_docket_ids(last_x_days: int) -> Set[int]:
    """Get docket IDs to update via iquery

    :param last_x_days: How many of the last days relative to today should we
    inspect? E.g. 1 means just today, 2 means today and yesterday, etc.
    :return: docket IDs for which we should crawl iquery
    """
    docket_ids = set()
    if hasattr(settings, "MATOMO_TOKEN"):
        try:
            r = requests.get(
                settings.MATOMO_REPORT_URL,
                timeout=10,
                params={
                    "idSite": settings.MATOMO_SITE_ID,
                    "module": "API",
                    "method": "Live.getLastVisitsDetails",
                    "period": "day",
                    "format": "json",
                    "date": "last%s" % last_x_days,
                    "token_auth": settings.MATOMO_TOKEN,
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
                "iQuery scraper was unable to get results from Matomo. Got "
                "exception: %s" % e
            )
        else:
            for item in j:
                for actiondetail in item["actionDetails"]:
                    url = actiondetail.get("url")
                    if url is None:
                        continue
                    match = re.search(
                        r"^https://www\.courtlistener\.com/docket/([0-9]+)/",
                        url,
                    )
                    if match is None:
                        continue
                    docket_ids.add(match.group(1))

    # Add in docket IDs that have docket alerts or are favorited
    docket_ids.update(DocketAlert.objects.values_list("docket", flat=True))
    docket_ids.update(
        Favorite.objects.exclude(docket_id=None).values_list(
            "docket_id", flat=True
        )
    )
    docket_ids.update(
        Docket.objects.filter(
            case_name__isnull=True, source__in=Docket.RECAP_SOURCES
        ).values_list("pk", flat=True)
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
        parser.add_argument(
            "--day-count",
            default=1,
            type=int,
            help="We will run iQuery for any case that was visited the last "
            "XX days, as tracked in Matomo. By default, it's just the last 1 "
            "day, but you can have it go back further via this parameter",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        do_missing_date_filed = options["do_missing_date_filed"]
        if do_missing_date_filed:
            docket_ids = get_docket_ids_missing_info(do_missing_date_filed)
        else:
            docket_ids = get_docket_ids(last_x_days=options["day_count"])
        # docket_ids = get_docket_ids().union(get_docket_ids_missing_info(100000)) #once initial scrape filling in date_filed is done, uncomment this to do these nightly
        logger.info(
            "iQuery crawling starting up. Will crawl %s dockets",
            len(docket_ids),
        )
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
                # Skip old terminated cases, but do them if we're missing date_filed or case_name
                continue

            if not d.pacer_case_id:
                # No case ID, can't crawl it. Skip.
                continue

            if d.court.jurisdiction not in [
                Court.FEDERAL_DISTRICT,
                Court.FEDERAL_BANKRUPTCY,
            ]:
                # Appeals or other kind of court that got sweapt up. Punt.
                continue

            update_docket_info_iquery.apply_async(
                args=(docket_id,), queue=queue
            )

        logger.info("Done!")
