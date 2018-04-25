# coding=utf-8
import logging
import lxml

import requests
from dateutil import parser
from juriscraper.pacer import PacerRssFeed

from cl.celery import app
from cl.lib.pacer import map_cl_to_pacer_id
from cl.recap_rss.models import RssFeedStatus
from cl.recap.tasks import find_docket_object, add_recap_source, \
    update_docket_metadata, add_docket_entries

logger = logging.getLogger(__name__)


def get_last_build_date(xml_string):
    """Get the last build date for an RSS feed"""
    doc = lxml.etree.fromstring(xml_string)
    last_build_date_str = doc.xpath('//lastBuildDate/text()')[0]
    return parser.parse(last_build_date_str, fuzzy=False)


def mark_status(status_obj, status_value):
    """Update the status_obj object with a status_value"""
    status_obj.status = status_value
    status_obj.save()


@app.task(bind=True, max_retries=5)
def check_if_feed_changed(self, court_pk, feed_status_pk, date_last_built):
    """Check if the feed changed

    For now, we do this in a very simple way, by using the lastBuildDate field
    and checking if it differs from the last time we checked. One thing that
    makes this approach suboptimal is that we know the `lastBuildDate` field
    varies around the time that the feeds are actually...um, built. For
    example, we've seen the same feed with two different values for this field
    around the time that it is built. When this happens, the two values tend to
    be off by about a minute or so.

    If we were being very careful and really optimizing when we crawled these
    feeds, this would cause us trouble because we'd detect a change in this
    field when the actual data hadn't changed. But because we only crawl the
    feeds at most once every five minutes, and because the gaps we've observed
    in this field tend to only be about one minute, we can get away with this.

    Other solutions/thoughts we can consider later:

     - If the difference between two lastBuildDate values is less than two
       minutes assume it's the same feed.
     - Use hashing of the feed to determine if it has changed.

    One other oddity here is that we use regex parsing to grab the
    lastBuildDate value. This is because parsing the feed properly can take
    several seconds for a big feed.
    """
    feed_status = RssFeedStatus.objects.get(pk=feed_status_pk)
    rss_feed = PacerRssFeed(map_cl_to_pacer_id(court_pk))
    try:
        rss_feed.query()
    except requests.RequestException as exc:
        logger.warning("Network error trying to get RSS feed at %s" % rss_feed.url)
        if self.request.retries == self.max_retries:
            # Abort. Unable to get the thing.
            mark_status(feed_status, RssFeedStatus.PROCESSING_FAILED)
            self.request.callbacks = None
            return
        mark_status(feed_status, RssFeedStatus.QUEUED_FOR_RETRY)
        raise self.retry(exc=exc, countdown=5)

    # Get the last time this feed was pulled successfully
    current_build_date = get_last_build_date(rss_feed.response.content)
    if date_last_built == current_build_date:
        # Abort. Nothing has changed here.
        self.request.callbacks = None
        mark_status(feed_status, RssFeedStatus.UNCHANGED)
        return
    else:
        feed_status.date_last_build = current_build_date
        feed_status.save()

    # Looks like we've got a change, folks. Let's do it.
    return rss_feed


@app.task
def merge_rss_feed_contents(rss_feed, court_pk):
    """Merge the rss feed contents into CourtListener

    :param rss_feed: A PacerRssFeed object that has already queried the feed.
    :param court_pk: The CourtListener court ID.
    :return:
    """
    rss_feed.parse()
    # RSS feeds are a list of normal Juriscraper docket objects.
    all_rds_created = []
    for docket in rss_feed.data:
        # XXX do some performance work here to early abort at some point.

        d, count = find_docket_object(court_pk, docket['pacer_case_id'],
                                      docket['docket_number'])
        if count > 1:
            logger.info("Found %s dockets during lookup. Choosing oldest." %
                        count)
            d = d.earliest('date_created')

        add_recap_source(d)
        update_docket_metadata(d, docket)
        if not d.pacer_case_id:
            d.pacer_case_id = docket['pacer_case_id']
        d.save()
        rds_created, _ = add_docket_entries(d, docket['docket_entries'])
        all_rds_created.extend([rd.pk for rd in rds_created])

    return all_rds_created


@app.task
def mark_status_successful(feed_status_pk):
    feed_status = RssFeedStatus.objects.get(pk=feed_status_pk)
    mark_status(feed_status, RssFeedStatus.PROCESSING_SUCCESSFUL)
