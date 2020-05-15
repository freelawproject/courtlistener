# coding=utf-8
from __future__ import print_function

import json
import re

import requests
from django.conf import settings

from cl.celery import app
from cl.lib.command_utils import VerboseCommand
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.pacer_session import get_or_cache_pacer_cookies
from cl.recap.mergers import (
    update_docket_metadata,
    add_bankruptcy_data_to_docket,
)
from cl.search.models import Docket
from cl.search.tasks import add_items_to_solr
from juriscraper.pacer import CaseQuery, PacerSession


def get_dockets():
    visits = requests.get(
        settings.MATOMO_URL,
        timeout=1,
        params={
            "idsite": settings.MATOMO_SITE_ID,
            "module": "API",
            "method": "Live.getLastVisitsDetails",
            "period": "week",
            "format": "json",
            "date": "today",
        },
    )
    visitsjson = json.loads(visits.text)
    for item in visitsjson[:10]:
        print(item["actionDetails"][0]["url"])
    urllist = [
        item["actionDetails"][0]["url"]
        if "url" in item["actionDetails"][0]
        else ""
        for item in visitsjson
    ]
    urllistasstring = "|".join(urllist)
    return set(re.findall("/docket/([0-9]+)/", urllistasstring))


@app.task()
def update_docket_info_iqeury(d_pk):
    cookies = get_or_cache_pacer_cookies(
        "pacer_scraper",
        settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    s = PacerSession(
        cookies=cookies,
        username=settings.PACER_USERNAME,
        password=settings.PACER_PASSWORD,
    )
    d = Docket.objects.get(pk=d_pk)
    report = CaseQuery(map_cl_to_pacer_id(d.court_id), s)
    report.query(d.pacer_case_id)
    d = update_docket_metadata(d, report.metadata)
    d.save()
    add_bankruptcy_data_to_docket(d, report.metadata)
    add_items_to_solr([d.pk], "search.Docket")


class Command(VerboseCommand):
    help = "Scrape PACER iquery report"

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        docket_list = get_dockets()
        for item in docket_list:
            update_docket_info_iqeury.delay(item)
