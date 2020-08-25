# coding=utf-8
import bz2
import errno
import json
import logging
import re
from datetime import timedelta

import requests
from dateutil import parser
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import transaction, IntegrityError
from django.utils.timezone import now
from juriscraper.pacer import PacerRssFeed

from cl.alerts.tasks import enqueue_docket_alert
from cl.celery import app
from cl.lib.crypto import sha256
from cl.lib.pacer import map_cl_to_pacer_id
from cl.recap.mergers import (
    add_docket_entries,
    find_docket_object,
    update_docket_metadata,
    add_bankruptcy_data_to_docket,
)
from cl.recap_rss.models import RssFeedStatus, RssItemCache, RssFeedData
from cl.recap_rss.utils import emails
from cl.search.models import Court

logger = logging.getLogger(__name__)


def update_entry_types(court_pk, description):
    """Check the entry types of a feed. If changed update our record and
    send an email.

    :param court_pk: The CL identifier for the court
    :param description: The <description> nodes in the feed
    :return: None
    """
    description = description.lower()
    if description == "public filings in the last 24 hours":
        # nyed: https://ecf.nyed.uscourts.gov/cgi-bin/readyDockets.pl
        new_entry_types = "all"
    elif description == "all docket entries.":
        # ared: https://ecf.ared.uscourts.gov/cgi-bin/rss_outside4.pl
        new_entry_types = "all"
    else:
        m = re.search(r"entries of type: (.+)", description)
        if not m:
            logger.error(
                "Unable to parse PACER RSS description: %s" % description
            )
            return
        new_entry_types = m.group(1)

    court = Court.objects.get(pk=court_pk)
    if court.pacer_rss_entry_types != new_entry_types:
        # PACER CHANGED AN RSS FEED.
        email = emails["changed_rss_feed"]
        send_mail(
            email["subject"] % court,
            email["body"]
            % (court, court.pacer_rss_entry_types, new_entry_types),
            email["from"],
            email["to"],
        )
        court.pacer_rss_entry_types = new_entry_types
        court.save()


def get_last_build_date(s):
    """Get the last build date for an RSS feed

    In this case we considered using lxml & xpath, which was 1000× faster than
    feedparser, but it turns out that using regex is *another* 1000× faster, so
    we use that. See: https://github.com/freelawproject/juriscraper/issues/195#issuecomment-385848344

    :param s: The content of the RSS feed as a string
    """
    # Most courts use lastBuildDate, but leave it up to ilnb to have pubDate.
    date_re = r"<(?P<tag>lastBuildDate|pubDate)>(.*?)</(?P=tag)>"
    m = re.search(date_re, s)
    if m is None:
        return None
    last_build_date_str = m.group(2)
    return parser.parse(last_build_date_str, fuzzy=False)


def mark_status(status_obj, status_value):
    """Update the status_obj object with a status_value"""
    status_obj.status = status_value
    status_obj.save()


def abort_or_retry(task, feed_status, exc):
    """Abort a task chain if there are no more retries. Else, retry it."""
    if task.request.retries == task.max_retries:
        # Abort and cut off the chain. No more retries.
        mark_status(feed_status, RssFeedStatus.PROCESSING_FAILED)
        task.request.chain = None
        return

    mark_status(feed_status, RssFeedStatus.QUEUED_FOR_RETRY)
    raise task.retry(exc=exc, countdown=5)


@app.task(bind=True, max_retries=0)
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

    :param court_pk: The CL ID for the court object.
    :param feed_status_pk: The CL ID for the status object.
    :param date_last_built: The last time the court was scraped.
    """
    feed_status = RssFeedStatus.objects.get(pk=feed_status_pk)
    rss_feed = PacerRssFeed(map_cl_to_pacer_id(court_pk))
    try:
        rss_feed.query()
    except requests.RequestException as exc:
        logger.warning(
            "Network error trying to get RSS feed at %s" % rss_feed.url
        )
        abort_or_retry(self, feed_status, exc)
        return

    content = rss_feed.response.content
    if not content:
        try:
            raise Exception(
                "Empty RSS document returned by PACER: %s"
                % feed_status.court_id
            )
        except Exception as exc:
            logger.warning(str(exc))
            abort_or_retry(self, feed_status, exc)
            return

    current_build_date = get_last_build_date(content)
    if current_build_date:
        feed_status.date_last_build = current_build_date
        feed_status.save()
    else:
        try:
            raise Exception(
                "No last build date in RSS document returned by "
                "PACER: %s" % feed_status.court_id
            )
        except Exception as exc:
            logger.warning(str(exc))
            abort_or_retry(self, feed_status, exc)
            return

    # Only check for early abortion during partial crawls.
    if date_last_built == current_build_date and not feed_status.is_sweep:
        logger.info(
            "%s: Feed has not changed since %s. Aborting.",
            feed_status.court_id,
            date_last_built,
        )
        # Abort. Nothing has changed here.
        self.request.chain = None
        mark_status(feed_status, RssFeedStatus.UNCHANGED)
        return

    logger.info(
        "%s: Feed changed or doing a sweep. Moving on to the merge."
        % feed_status.court_id
    )
    rss_feed.parse()
    logger.info(
        "%s: Got %s results to merge."
        % (feed_status.court_id, len(rss_feed.data))
    )

    # Update RSS entry types in Court table
    update_entry_types(court_pk, rss_feed.feed.feed.description)

    # Save the feed to the DB
    feed_data = RssFeedData(court_id=court_pk)
    try:
        feed_data.filepath.save(
            "rss.xml.bz2", ContentFile(bz2.compress(content))
        )
    except OSError as exc:
        if exc.errno == errno.EIO:
            abort_or_retry(self, feed_status, exc)
        else:
            raise exc

    return rss_feed.data


def hash_item(item):
    """Hash an RSS item. Item should be a dict at this stage"""
    # Stringify, normalizing dates to strings.
    item_j = json.dumps(item, sort_keys=True, default=str)
    item_hash = sha256(item_j)
    return item_hash


def is_cached(item_hash):
    """Check if a hash is in the RSS Item Cache"""
    return RssItemCache.objects.filter(hash=item_hash).exists()


def cache_hash(item_hash):
    """Add a new hash to the RSS Item Cache

    :param item_hash: A SHA1 hash you wish to cache.
    :returns True if successful, False if not.
    """
    try:
        RssItemCache.objects.create(hash=item_hash)
    except IntegrityError:
        # Happens during race conditions or when you try to cache something
        # that's already in there.
        return False
    else:
        return True


@app.task(bind=True, max_retries=1)
def merge_rss_feed_contents(self, feed_data, court_pk, metadata_only):
    """Merge the rss feed contents into CourtListener

    :param self: The Celery task
    :param feed_data: The data parameter of a PacerRssFeed object that has
    already queried the feed and been parsed.
    :param court_pk: The CourtListener court ID.
    :param metadata_only: Whether to only do metadata and skip docket entries.
    :returns Dict containing keys:
      d_pks_to_alert: A list of (docket, alert_time) tuples for sending alerts
      rds_for_solr: A list of RECAPDocument PKs for updating in Solr
    """
    start_time = now()

    # RSS feeds are a list of normal Juriscraper docket objects.
    all_rds_created = []
    d_pks_to_alert = []
    for docket in feed_data:
        item_hash = hash_item(docket)
        if is_cached(item_hash):
            continue

        with transaction.atomic():
            cached_ok = cache_hash(item_hash)
            if not cached_ok:
                # The item is already in the cache, ergo it's getting processed
                # in another thread/process and we had a race condition.
                continue
            d, docket_count = find_docket_object(
                court_pk, docket["pacer_case_id"], docket["docket_number"]
            )
            if docket_count > 1:
                logger.info(
                    "Found %s dockets during lookup. Choosing "
                    "oldest." % docket_count
                )
                d = d.earliest("date_created")

            d.add_recap_source()
            update_docket_metadata(d, docket)
            if not d.pacer_case_id:
                d.pacer_case_id = docket["pacer_case_id"]
            try:
                d.save()
                add_bankruptcy_data_to_docket(d, docket)
            except IntegrityError as exc:
                # The docket was created while we looked it up. Retry and it
                # should associate with the new one instead.
                raise self.retry(exc=exc)
            if metadata_only:
                continue

            rds_created, content_updated = add_docket_entries(
                d, docket["docket_entries"]
            )

        if content_updated and docket_count > 0:
            newly_enqueued = enqueue_docket_alert(d.pk)
            if newly_enqueued:
                d_pks_to_alert.append((d.pk, start_time))

        all_rds_created.extend([rd.pk for rd in rds_created])

    logger.info(
        "%s: Sending %s new RECAP documents to Solr for indexing and "
        "sending %s dockets for alerts.",
        court_pk,
        len(all_rds_created),
        len(d_pks_to_alert),
    )
    return {"d_pks_to_alert": d_pks_to_alert, "rds_for_solr": all_rds_created}


@app.task
def mark_status_successful(feed_status_pk):
    feed_status = RssFeedStatus.objects.get(pk=feed_status_pk)
    logger.info("Marking %s as a success." % feed_status.court_id)
    mark_status(feed_status, RssFeedStatus.PROCESSING_SUCCESSFUL)


@app.task
def trim_rss_data(cache_days=2, status_days=14):
    """Trim the various tracking objects used during RSS parsing

    :param cache_days: RssItemCache objects older than this number of days will
    be deleted
    :param status_days: RssFeedStatus objects older than this number of days
    will be deleted.
    """
    logger.info("Trimming RSS tracking items.")
    RssItemCache.objects.filter(
        date_created__lt=now() - timedelta(days=cache_days)
    ).delete()
    RssFeedStatus.objects.filter(
        date_created__lt=now() - timedelta(days=status_days)
    ).delete()
