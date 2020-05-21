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
from cl.search.models import Docket


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
    return docket_ids


class Command(VerboseCommand):
    help = "Scrape PACER iquery report"

    def add_arguments(self, parser):
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the tasks should be processed.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        docket_ids = get_docket_ids()
        logger.info(
            "iQuery crawling starting up. Will crawl %s dockets",
            len(docket_ids),
        )
        queue = options["queue"]
        throttle = CeleryThrottle(queue_name=queue)
        now = datetime.now().date
        for i, docket_id in enumerate(docket_ids):
            throttle.maybe_wait()

            if i % 500 == 0:
                logger.info("Sent %s items to celery for crawling so far.")

            d = Docket.objects.get(pk=docket_id).only(
                "date_terminated", "date_last_filing", "pacer_case_id"
            )
            too_many_days_old = 90
            if all(
                [
                    d.date_terminated,
                    now - d.date_terminated > too_many_days_old,
                    now - d.date_last_filing > too_many_days_old,
                ]
            ):
                # Skip old terminated cases
                continue

            if not d.pacer_case_id:
                # No case ID, can't crawl it. Skip.
                continue

            update_docket_info_iquery.apply_async(
                args=(docket_id,), queue=queue
            )

        logger.info("Done!")
