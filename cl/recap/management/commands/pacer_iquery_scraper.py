# coding=utf-8
from __future__ import print_function

import json
import re

import requests
from django.conf import settings

from cl.alerts.models import DocketAlert
from cl.lib.command_utils import VerboseCommand
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
            docket_ids.update(re.findall("/docket/[0-9]+/", url))
    docket_ids.update(
        [a["docket"] for a in DocketAlert.objects.values("docket")]
    )
    return docket_ids


class Command(VerboseCommand):
    help = "Scrape PACER iquery report"

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        docket_list = get_dockets()
        for item in docket_list:
            update_docket_info_iquery.delay(item)
