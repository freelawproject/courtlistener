import bz2
import errno
import json
import logging
import re
from calendar import SATURDAY, SUNDAY
from datetime import datetime, timedelta
from typing import Optional

import requests
from celery import Task
from dateparser import parse
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils.timezone import now
from juriscraper.pacer import PacerRssFeed
from pytz import timezone
from requests import HTTPError

from cl.alerts.tasks import enqueue_docket_alert
from cl.celery_init import app
from cl.lib.crypto import sha256
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.types import EmailType
from cl.recap.constants import COURT_TIMEZONES
from cl.recap.mergers import (
    add_bankruptcy_data_to_docket,
    add_docket_entries,
    find_docket_object,
    update_docket_metadata,
)
from cl.recap_rss.models import RssFeedData, RssFeedStatus, RssItemCache
from cl.recap_rss.utils import emails
from cl.search.models import Court

logger = logging.getLogger(__name__)


def update_entry_types(court_pk: str, description: str) -> None:
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
                f"Unable to parse PACER RSS description: {description}"
            )
            return
        new_entry_types = m.group(1)

    court = Court.objects.get(pk=court_pk)
    if court.pacer_rss_entry_types != new_entry_types:
        # PACER CHANGED AN RSS FEED.
        email: EmailType = emails["changed_rss_feed"]
        send_mail(
            email["subject"] % court,
            email["body"]
            % (court, court.pacer_rss_entry_types, new_entry_types),
            email["from_email"],
            email["to"],
        )
        court.pacer_rss_entry_types = new_entry_types
        court.save()


def get_last_build_date(b: bytes) -> Optional[datetime]:
    """Get the last build date for an RSS feed

    In this case we considered using lxml & xpath, which was 1000× faster than
    feedparser, but it turns out that using regex is *another* 1000× faster, so
    we use that. See: https://github.com/freelawproject/juriscraper/issues/195#issuecomment-385848344

    :param b: The content of the RSS feed as a string
    :type b: bytes! This is a performance enhancement, but perhaps a premature
    one. Depending on how this function returns we might not need to decode
    the byte-string to text, so we just regex it as is.
    """
    # Most courts use lastBuildDate, but leave it up to ilnb to have pubDate.
    date_re = rb"<(?P<tag>lastBuildDate|pubDate)>(.*?)</(?P=tag)>"
    m = re.search(date_re, b)
    if m is None:
        return None
    last_build_date_b = m.group(2)
    return parse(last_build_date_b.decode())


def alert_on_staleness(
    current_build_date: datetime,
    court_id: str,
    url: str,
) -> None:
    """Send an alert email if a feed goes stale on a weekday, according to its
    timezone. Slow down after the first day.

    :param current_build_date: When the feed was updated
    :param court_id: The CL ID of the court
    :param url: The URL for the feed
    """
    _now = now()
    staleness = _now - current_build_date

    # If a feed is not stale, do not send an alert.
    staleness_limit = timedelta(minutes=2 * 60)
    if staleness < staleness_limit:
        return

    # Maintenance is frequently done on weekends, causing staleness. Don't
    # send alerts on weekends.
    court_tz = timezone(COURT_TIMEZONES.get(court_id, "US/Pacific"))
    court_now = _now.astimezone(court_tz)
    if court_now.weekday() in [SATURDAY, SUNDAY]:
        return

    # If it's really stale, don't send alerts except during hours evenly
    # divisible by six to slow down alerts.
    on_a_sixth = _now.hour % 6 == 0
    really_stale = timedelta(minutes=60 * 24)
    if (staleness > really_stale) and not on_a_sixth:
        return

    # All limits have passed; send an alert
    email: EmailType = emails["stale_feed"]
    send_mail(
        email["subject"] % court_id,
        email["body"]
        % (court_id, round(staleness.total_seconds() / 60, 2), url),
        email["from_email"],
        email["to"],
    )


def mark_status(status_obj, status_value):
    """Update the status_obj object with a status_value"""
    status_obj.status = status_value
    status_obj.save()


def abort_task(task: Task, feed_status: RssFeedStatus):
    """Abort RSS tasks without retry.

    We don't want to retry RSS tasks because they'll get retried by the
    daemon anyway, and because they have log timeouts. Better just to let
    them die.
    """
    mark_status(feed_status, RssFeedStatus.PROCESSING_FAILED)
    task.request.chain = None
    return


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
    except requests.RequestException:
        logger.warning(
            f"Network error trying to get RSS feed at {rss_feed.url}"
        )
        abort_task(self, feed_status)
        return

    content = rss_feed.response.content
    if not content:
        try:
            raise Exception(
                f"Empty RSS document returned by PACER: {feed_status.court_id}"
            )
        except Exception as exc:
            logger.warning(str(exc))
            abort_task(self, feed_status)
            return

    try:
        rss_feed.response.raise_for_status()
    except HTTPError as exc:
        logger.warning(
            f"RSS feed down at '{court_pk}' "
            f"({rss_feed.response.status_code}). {exc}"
        )
        abort_task(self, feed_status)
        return

    current_build_date = get_last_build_date(content)
    if current_build_date:
        alert_on_staleness(
            current_build_date, feed_status.court_id, rss_feed.url
        )
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
            abort_task(self, feed_status)
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
        f"{feed_status.court_id}: Got {len(rss_feed.data)} results to merge."
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
            abort_task(self, feed_status)
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
def merge_rss_feed_contents(self, feed_data, court_pk, metadata_only=False):
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
            d = find_docket_object(
                court_pk, docket["pacer_case_id"], docket["docket_number"]
            )

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

            des_returned, rds_created, content_updated = add_docket_entries(
                d, docket["docket_entries"]
            )

        if content_updated:
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
    logger.info(f"Marking {feed_status.court_id} as a success.")
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
