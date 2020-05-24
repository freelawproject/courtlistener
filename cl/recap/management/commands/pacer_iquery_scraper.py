# coding=utf-8
from __future__ import print_function

import re
from datetime import datetime

import requests
from django.conf import settings

from cl.alerts.models import DocketAlert
from cl.favorites.models import Favorite
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.tasks import update_docket_info_iquery
from cl.search.models import Docket, Court


def get_docket_ids_missing_info(num_to_get):
    docket_ids = set()
    docket_ids.update(
        Docket.objects.filter(
            date_filed__isnull=True, source__in=Docket.RECAP_SOURCES
        )
        .order_by("-view_count")[:num_to_get]
        .values_list("pk", flat=True)
    )
    return docket_ids


def get_docket_ids():
    visits = requests.get(
        settings.MATOMO_REPORT_URL,
        timeout=10,
        params={
            "idSite": settings.MATOMO_SITE_ID,
            "module": "API",
            "method": "Live.getLastVisitsDetails",
            "period": "week",
            "format": "json",
            "date": "today",
            "token_auth": settings.MATOMO_TOKEN,
        },
    )
    docket_ids = set()
    for item in visits.json():
        for actiondetail in item["actionDetails"]:
            url = actiondetail.get("url")
            if url is None:
                continue
            match = re.search(
                "^https://www.courtlistener\.com/docket/([0-9]+)/", url
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
            default=False,
            help="Whether to scrape dockets with missing date_filed field."
            "if set, should be the number of dockets to scrape",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        do_missing_date_filed = options["do_missing_date_filed"]
        if do_missing_date_filed:
            docket_ids = get_docket_ids_missing_info(do_missing_date_filed)
        else:
            docket_ids = get_docket_ids()
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
