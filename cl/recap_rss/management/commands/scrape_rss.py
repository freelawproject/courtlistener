import fcntl
import sys
import time
from datetime import timedelta, datetime

from celery.canvas import chain
from django.utils.timezone import now, make_aware

from cl.lib.command_utils import VerboseCommand
from cl.recap_rss.models import RssFeedStatus
from cl.recap_rss.tasks import check_if_feed_changed, merge_rss_feed_contents, \
    mark_status_successful
from cl.search.models import Court
from cl.search.tasks import add_or_update_recap_document


class Command(VerboseCommand):
    help = 'Scrape PACER RSS feeds'

    RSS_MAX_VISIT_FREQUENCY = 5 * 60
    RSS_MAX_PROCESSING_DURATION = 10 * 60
    DELAY_BETWEEN_ITERATIONS = 1 * 60

    def add_arguments(self, parser):
        parser.add_argument(
            '--courts',
            type=str,
            default=['all'],
            nargs="*",
            help="The courts that you wish to parse.",
        )
        parser.add_argument(
            '--iterations',
            type=int,
            default=0,
            help="The number of iterations to take. Default is 0, which means "
                 "to loop forever",
        )
        parser.add_argument(
            '--sweep',
            default=False,
            action='store_true',
            help="Ignore anything that says to stop and download everything "
                 "you see. Don't create duplicates. Recommend running this "
                 "with --iterations 1",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        if options['sweep'] is False:
            # Only allow one script at a time per court combination.
            # Note that multiple scripts on multiple machines could still be
            # run.
            court_str = '-'.join(sorted(options['courts']))
            with open('/tmp/rss-scraper-%s.pid' % court_str, 'w') as fp:
                try:
                    fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except IOError:
                    print("Another instance of this program is running with "
                          "for this combination of courts. Only one instance "
                          "can crawl these courts at a time: '%s'" % court_str)
                    sys.exit(1)

        # Loop over the PACER sites that have RSS feeds and see if they're
        # ready to do.
        courts = Court.objects.filter(
            jurisdiction__in=[
                Court.FEDERAL_BANKRUPTCY,
                Court.FEDERAL_DISTRICT,
            ],
            pacer_has_rss_feed=True,
        )
        if options['courts'] != ['all']:
            courts = courts.filter(pk__in=options['courts'])

        iterations_completed = 0
        while options['iterations'] == 0 or \
                iterations_completed < options['iterations']:
            for court in courts:
                # Check the last time we successfully got the feed
                try:
                    feed_status = RssFeedStatus.objects.filter(
                        court=court,
                        is_sweep=options['sweep'],
                        status__in=[
                            RssFeedStatus.PROCESSING_SUCCESSFUL,
                            RssFeedStatus.UNCHANGED,
                            RssFeedStatus.PROCESSING_IN_PROGRESS,
                        ]
                    ).latest('date_created')
                except RssFeedStatus.DoesNotExist:
                    # First time running it or status items have been nuked by
                    # an admin. Make a dummy object, but no need to actually
                    # save it to the DB. Make it old.
                    lincolns_birthday = make_aware(datetime(1809, 2, 12))
                    feed_status = RssFeedStatus(
                        date_created=lincolns_birthday,
                        date_last_build=lincolns_birthday,
                        is_sweep=options['sweep'],
                    )
                if options['courts'] == ['all'] and options['sweep'] is False:
                    # If it's all courts and it's not a sweep, check if we did
                    # it recently.
                    five_minutes_ago = now() - timedelta(
                        seconds=self.RSS_MAX_VISIT_FREQUENCY)
                    if feed_status.date_created > five_minutes_ago:
                        # Processed within last five minutes. Try next court.
                        continue

                # Give a court ten minutes to complete during non-sweep crawls
                ten_minutes_ago = now() - timedelta(
                    seconds=self.RSS_MAX_PROCESSING_DURATION)
                if all([
                    options['sweep'] is False,
                    feed_status.status == RssFeedStatus.PROCESSING_IN_PROGRESS,
                    feed_status.date_created < ten_minutes_ago
                ]):
                    continue

                # The court is ripe! Crawl it if it has changed.
                # Make a new object to track the attempted crawl.
                new_status = RssFeedStatus.objects.create(
                    court_id=court.pk,
                    status=RssFeedStatus.PROCESSING_IN_PROGRESS,
                    is_sweep=options['sweep'],
                )

                # Check if the item needs crawling, and crawl it if so.
                chain(
                    check_if_feed_changed.s(court.pk, new_status.pk,
                                            feed_status.date_last_build),
                    merge_rss_feed_contents.s(court.pk, new_status.pk),
                    # Update recap *documents*, not *dockets*. Updating dockets
                    # requires much more work, and we don't expect to get much
                    # docket information from the RSS feeds. RSS feeds also
                    # have information about hundreds or thousands of
                    # dockets. Updating them all would be very bad.
                    add_or_update_recap_document.s(),
                    mark_status_successful.si(new_status.pk),
                ).apply_async()

            # Wait one minute, then attempt all courts again if iterations not
            # exceeded.
            iterations_completed += 1
            time.sleep(self.DELAY_BETWEEN_ITERATIONS)
