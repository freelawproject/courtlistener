# coding=utf-8
from __future__ import print_function

import time
from datetime import datetime, timedelta

from django.db.models import Count

from cl.alerts.models import DocketAlert
from cl.alerts.tasks import update_docket_and_send_alert
from cl.lib.command_utils import VerboseCommand
from cl.search.models import Docket


def check_schedule(now):
    """Should we run the alerts?

    Alerts are sent according to the following rules:

                                   Num alerts
                             +---+---+---+-----+------+
                             | 0 | 1 | 2 | 3-9 | >=10 |
          │                  +---+---+---+-----+------+
          │         30 after | N | N | N |  N  |  Y   |
       W  │                  +---+---+---+-----+------+
       H  │           hourly | N | N | N |  Y  |  Y   |
       E  │                  +---+---+---+-----+------+
       N  │  6am, 6pm & noon | N | N | Y |  Y  |  Y   |
       ?  │                  +---+---+---+-----+------+
          │         Midnight | N | Y | Y |  Y  |  Y   |
          │                  +---+---+---+-----+------+
          │         Midnight | N | Y | Y |  Y  |  Y   | <-- Also old term. cases
                      Sunday +---+---+---+-----+------+
                               │
                               └─never

    :param now: datetime of when the current run was started
    :return: tuple of (min_alerts, crawl_types). min_alerts is the minumum
    number of alerts a docket must have to run alerts. crawle_types is a set
    of the types of items to crawl.
    """
    crawl_types = set()
    min_alerts = 0
    if now.minute == 30:
        # we're on a half hour schedule
        min_alerts = 10
    elif now.minute == 0:
        if now.hour == 0:
            # At midnight do all alerts + terminated
            min_alerts = 1
            crawl_types.add("terminated")
        elif now.hour in [6, 12, 18]:
            # Three extra times daily
            min_alerts = 2
        else:
            # Default hourly schedule
            min_alerts = 3

    if now.minute == 0 and now.hour == 0 and now.weekday() == 6:
        # check old terminated dockets (>90 days) on Sunday
        crawl_types.add("old_terminated")

    return min_alerts, crawl_types


class Command(VerboseCommand):
    help = "Scrape PACER iquery report and send alerts"

    def add_arguments(self, parser):
        parser.add_argument(
            "--test_date",
            type=datetime.date,
            default=None,
            help="The number of dockets to check. Default is None, which means "
            "to check everything",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        while True:
            now = datetime.now()
            crawl_types = set()

            if now.minute != 30 and now.minute != 0:
                # Early abort unless debugging. Nothing fires except on the
                # hour and the half.
                debug = False
                if not debug:
                    time.sleep(30)
                    continue
                min_alerts = 0
                crawl_types.add("old_terminated")
            else:
                min_alerts, crawl_types = check_schedule(now)

            # list of all dockets that need to be checked
            docket_list = DocketAlert.objects.values("docket").annotate(
                alerts_count=Count("id")
            )
            test_date = options["test_date"]
            for item in docket_list:
                if item["alerts_count"] < min_alerts:
                    continue
                docket = Docket.objects.get(pk=item["docket"])
                if (
                    test_date
                    and docket.date_filed
                    and docket.date_filed > test_date
                ):
                    continue
                terminated_recently = (
                    "terminated" in crawl_types
                    and docket.date_terminated
                    and (now.date() - docket.date_last_filing) < 90
                )
                # Send alerts for non-terminated, recently terminated, or
                # old terminated dockets if properly timed
                if (
                    docket.date_terminated is None
                    or terminated_recently
                    or "old_terminated" in crawl_types
                ):
                    since = (
                        DocketAlert.objects.filter(docket=docket)
                        .latest("date_created")
                        .date_last_hit
                    )
                    if since is None:
                        # if never hit, check if new filing since yesterday
                        since = now - timedelta(days=1)

                    update_docket_and_send_alert.delay(docket.pk, since)

            time.sleep(60)
