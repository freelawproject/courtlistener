from __future__ import print_function

import time
from datetime import datetime, timedelta

from django.db.models import Count

from cl.alerts.models import DocketAlert
from cl.alerts.tasks import update_docket_and_send_alert
from cl.lib.command_utils import VerboseCommand
from cl.search.models import Docket


class Command(VerboseCommand):
    help = "Scrape PACER for all alerts"

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        while True:
            date = datetime.now()
            crawl_terminated = False
            crawl_old_terminated = False
            if date.minute == 30:
                # we're on a half hour schedule, so only scrape dockets with at least 10 alerts
                min_alerts = 10
            elif date.minute == 0:  # we're on an hour schedule
                if date.hour % 6 == 0:
                    # this triggers 4 times a day, for dockets with at least 2 alerts
                    min_alerts = 2
                    if date.hour == 0:
                        # triggers once per day, check everything but terminated
                        min_alerts = 1
                        crawl_terminated = True
                        # check terminated dockets once a day

                        if date.weekday() == 6:
                            # check old terminated dockets (>90 days) on Sunday
                            crawl_old_terminated = True
                else:
                    min_alerts = 3  # default hourly check for dockets with at least 3 alerts
            else:  # not on an hour or a half hour schedule, so return
                debug = False  # makes it easy to test: just change this line to True and it'll do every docket
                if not debug:
                    time.sleep(30)
                    continue
                min_alerts = 0
                crawl_old_terminated = True

            # list of all dockets that need to be checked
            docket_list = DocketAlert.objects.values("docket").annotate(
                alerts=Count("id")
            )
            for item in docket_list:
                if item["alerts"] >= min_alerts:
                    docket = Docket.objects.get(pk=item["docket"])
                    docket_not_terminated = not docket.date_terminated
                    terminated_recently = (
                        crawl_terminated
                        and (date.date() - docket.date_last_filing) < 90
                    )
                    # weekly check of all dockets including terminated, or daily check  of terminated dockets with filings in last 90 days
                    if (
                        docket_not_terminated
                        or crawl_old_terminated
                        or terminated_recently
                    ):
                        since = DocketAlert.objects.filter(docket=docket)[
                            0
                        ].date_last_hit or date - timedelta(days=1)
                        # if never hit, check if new filing since yesterday
                        update_docket_and_send_alert.delay(docket, since)

            time.sleep(60)
