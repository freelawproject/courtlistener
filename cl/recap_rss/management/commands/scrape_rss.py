import fcntl
import sys
import time
from datetime import datetime, timedelta

from celery.canvas import chain
from django.utils.timezone import make_aware, now

from cl.alerts.tasks import send_alerts_and_webhooks
from cl.lib.command_utils import VerboseCommand
from cl.recap_rss.models import RssFeedStatus
from cl.recap_rss.tasks import (
    check_if_feed_changed,
    mark_status_successful,
    merge_rss_feed_contents,
    trim_rss_data,
)
from cl.search.models import Court
from cl.search.tasks import add_items_to_solr


class Command(VerboseCommand):
    help = "Scrape PACER RSS feeds"

    RSS_MAX_VISIT_FREQUENCY = 5 * 60
    RSS_MAX_PROCESSING_DURATION = 10 * 60
    DELAY_BETWEEN_ITERATIONS = 1 * 60
    DELAY_BETWEEN_CACHE_TRIMS = 60 * 60

    def add_arguments(self, parser):
        parser.add_argument(
            "--courts",
            type=str,
            default=["all"],
            nargs="*",
            help="The courts that you wish to parse.",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=0,
            help="The number of iterations to take. Default is 0, which means "
            "to loop forever",
        )
        parser.add_argument(
            "--sweep",
            default=False,
            action="store_true",
            help="During normal usage, there are a variety of checks in place "
            "that ensure that you don't scrape an RSS feed too soon, "
            "scrape one that hasn't changed, or scrape individual items "
            "that have already been added to the DB. Use this flag to "
            "ignore all of that and just download everything in the "
            "requested feeds. Don't create duplicates. Recommend running "
            "this with --iterations 1",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        if options["sweep"] is False:
            # Only allow one script at a time per court combination.
            # Note that multiple scripts on multiple machines could still be
            # run.
            court_str = "-".join(sorted(options["courts"]))
            with open(f"/tmp/rss-scraper-{court_str}.pid", "w") as fp:
                try:
                    fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except IOError:
                    print(
                        "Another instance of this program is running with "
                        "this combination of courts. Only one instance "
                        "can crawl these courts at a time: '%s'" % court_str
                    )
                    sys.exit(1)

        # Loop over the PACER sites that have RSS feeds and see if they're
        # ready to do.
        courts = Court.federal_courts.all_pacer_courts().filter(
            pacer_has_rss_feed=True,
        )
        if options["courts"] != ["all"]:
            courts = courts.filter(pk__in=options["courts"])

        iterations_completed = 0
        last_trim_date = None
        while (
            options["iterations"] == 0
            or iterations_completed < options["iterations"]
        ):
            for court in courts:
                # Check the last time we successfully got the feed
                try:
                    feed_status = RssFeedStatus.objects.filter(
                        court=court,
                        is_sweep=options["sweep"],
                        status__in=[
                            RssFeedStatus.PROCESSING_SUCCESSFUL,
                            RssFeedStatus.UNCHANGED,
                            RssFeedStatus.PROCESSING_IN_PROGRESS,
                        ],
                    ).latest("date_created")
                except RssFeedStatus.DoesNotExist:
                    # First time running it or status items have been nuked by
                    # an admin. Make a dummy object, but no need to actually
                    # save it to the DB. Make it old.
                    lincolns_birthday = make_aware(datetime(1809, 2, 12))
                    feed_status = RssFeedStatus(
                        date_created=lincolns_birthday,
                        date_last_build=lincolns_birthday,
                        is_sweep=options["sweep"],
                    )
                if options["courts"] == ["all"] and options["sweep"] is False:
                    # If it's all courts and it's not a sweep, check if we did
                    # it recently.
                    max_visit_ago = now() - timedelta(
                        seconds=self.RSS_MAX_VISIT_FREQUENCY
                    )
                    if feed_status.date_created > max_visit_ago:
                        # Processed too recently. Try next court.
                        continue

                # Don't crawl a court if it says it's been in progress just a
                # little while. It's probably queued and on the way.
                processing_cutoff = now() - timedelta(
                    seconds=self.RSS_MAX_PROCESSING_DURATION
                )
                if all(
                    [
                        options["sweep"] is False,
                        feed_status.status
                        == RssFeedStatus.PROCESSING_IN_PROGRESS,
                        feed_status.date_created > processing_cutoff,
                    ]
                ):
                    continue

                # The court is ripe! Crawl it if it has changed.
                # Make a new object to track the attempted crawl.
                new_status = RssFeedStatus.objects.create(
                    court_id=court.pk,
                    status=RssFeedStatus.PROCESSING_IN_PROGRESS,
                    is_sweep=options["sweep"],
                )

                # Check if the item needs crawling, and crawl it if so.
                chain(
                    check_if_feed_changed.s(
                        court.pk, new_status.pk, feed_status.date_last_build
                    ),
                    merge_rss_feed_contents.s(court.pk),
                    send_alerts_and_webhooks.s(),
                    # Update recap *documents*, not *dockets*. Updating dockets
                    # requires much more work, and we don't expect to get much
                    # docket information from the RSS feeds. RSS feeds also
                    # have information about hundreds or thousands of
                    # dockets. Updating them all would be very bad.
                    add_items_to_solr.s("search.RECAPDocument"),
                    mark_status_successful.si(new_status.pk),
                ).apply_async()

            # Trim if not too recently trimmed.
            trim_cutoff_date = now() - timedelta(
                seconds=self.DELAY_BETWEEN_CACHE_TRIMS
            )
            if last_trim_date is None or trim_cutoff_date > last_trim_date:
                trim_rss_data.delay()
                last_trim_date = now()

            # Wait, then attempt the courts again if iterations not exceeded or
            # iterations == 0 (loop forever)
            iterations_completed += 1
            remaining_iterations = options["iterations"] - iterations_completed
            if options["iterations"] == 0 or remaining_iterations > 0:
                time.sleep(self.DELAY_BETWEEN_ITERATIONS)
