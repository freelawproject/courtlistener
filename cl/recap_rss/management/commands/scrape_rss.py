import time
from datetime import timedelta, datetime

from celery.canvas import chain
from django.utils.timezone import now, make_aware

from cl.lib.command_utils import VerboseCommand
from cl.search.models import Court
from cl.recap_rss.models import RssFeedStatus
from cl.recap_rss.tasks import check_if_feed_changed, merge_rss_feed_contents, \
    mark_status_successful
from cl.search.tasks import add_or_update_recap_document


class Command(VerboseCommand):
    help = 'Scrape PACER RSS feeds'

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)

        # xxx do flock here to ensure only one instance.

        # Loop over the PACER sites that have RSS feeds and see if they're
        # ready to do.
        courts = Court.objects.filter(jurisdiction__in=[
            Court.FEDERAL_BANKRUPTCY,
            Court.FEDERAL_DISTRICT,
        ], end_date__isnull=True)
        while True:
            for court in courts:
                # Check the last time we successfully got the feed
                try:
                    feed_status = RssFeedStatus.objects.filter(
                        court=court,
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
                    )

                five_minutes_ago = now() - timedelta(minutes=5)
                if feed_status.date_created > five_minutes_ago:
                    # Processed within last five minutes. Press on.
                    continue
                elif feed_status.status == RssFeedStatus.PROCESSING_IN_PROGRESS:
                    # Still working on it. Press on.
                    continue
                else:
                    # Check if the item needs crawling, and crawl it if so.
                    new_status = RssFeedStatus.objects.create(
                        court_id=court.pk,
                        status=RssFeedStatus.PROCESSING_IN_PROGRESS
                    )
                    chain(
                        check_if_feed_changed.s(court.pk, new_status.pk,
                                                feed_status.date_last_build),
                        merge_rss_feed_contents.s(court.pk),
                        # Here, we update recap *documents*, not *dockets*. The
                        # reason for this is that updating dockets requires
                        # much more work, and we don't expect to get much
                        # docket information from the RSS feeds. RSS feeds also
                        # have information about hundreds or thousands of
                        # dockets. Updating them all would be very bad.
                        add_or_update_recap_document.s(),
                        mark_status_successful.si(new_status.pk),
                    ).apply_async()

            # Wait one minute, then do all courts again.
            time.sleep(60)

