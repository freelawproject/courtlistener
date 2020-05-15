# coding=utf-8
from __future__ import print_function

import re

import requests
from django.conf import settings

from cl.alerts.models import DocketAlert
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.tasks import update_docket_info_iquery


def get_dockets():
    visits = requests.get(
        settings.MATOMO_REPORT_URL,
        timeout=1,
        params={
            "idsite": settings.MATOMO_SITE_ID,
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
            match = re.search("/docket/([0-9]+)/", url)
            if match is None:
                continue
            docket_ids.add(match.group(1))
    docket_ids.update(
        [a["docket"] for a in DocketAlert.objects.values("docket")]
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
        docket_list = get_dockets()
        logger.info(
            "iQuery crawling starting up. Will crawl %s dockets",
            len(docket_list),
        )
        queue = options["queue"]
        throttle = CeleryThrottle(queue_name=queue)
        for i, item in enumerate(docket_list):
            throttle.maybe_wait()

            if i % 500 == 0:
                logger.info("Sent %s items to celery for crawling so far.")

            update_docket_info_iquery.apply_async(args=(item,), queue=queue)

        logger.info("Done!")
