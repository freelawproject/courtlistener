from __future__ import print_function
import sys

from django.db import IntegrityError
from django.db.models import Q, Count
from lxml.etree import XMLSyntaxError

from cl.lib.command_utils import VerboseCommand
from cl.lib.db_tools import queryset_generator
from cl.search.models import Docket
from cl.alerts.models import DocketAlert
from cl.alerts.tasks import send_docket_alert
from datetime import datetime


class Command(VerboseCommand):
    help = "Scrape PACER for all alerts"

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        date = datetime.now()

        terminated = False
        old_terminated = False
        if (
            date.minute == 30
        ):  # we're on a half hour schedule, so only scrape dockets with at least 10 alerts
            min_alerts = 10
        elif date.minute == 0:  # we're on an hour schedule
            if (
                date.hour % 6
            ) == 0:  # this triggers 4 times a day, for dockets with at least 2 alerts
                min_alerts = 2
            elif (
                date.hour == 0
            ):  # triggers once per day, check everything but terminated
                min_alerts = 1
                terminated = True  # check terminated dockets once a day
                if (
                    date.weekday() == 6
                ):  # check old terminated dockets (>90 days) on Sunday
                    old_terminated = True
            else:
                min_alerts = 3  # default hourly check for dockets with at least 3 alerts
        else:  # not on an hour or a half hour schedule, so return
            return
        # list of all dockets that need to be checked
        docket_list = DocketAlert.objects.values("docket").annotate(
            alerts=Count("id")
        )
        for item in docket_list:
            if item["alerts"] >= min_alerts:
                docket = Docket.objects.get(pk=item["docket"])
                if (
                    not docket.date_terminated
                    or old_terminated
                    or (
                        terminated
                        and (date.date() - docket.date_last_filing) < 90
                    )
                ):  # weekly check of all dockets including terminated, or daily check  of terminated dockets with filings in last 90 days
                    send_docket_alert.delay(docket.pk, date)
        return
