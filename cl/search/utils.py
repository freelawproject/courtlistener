from datetime import UTC, datetime, timedelta
from urllib import parse

import requests
from cache_memoize import cache_memoize
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import QuerySet, Sum, Value
from django.db.models.functions import Coalesce, Floor
from django.utils.timezone import make_aware, now
from requests import Response

from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import naturalduration
from cl.lib.cloud_front import invalidate_cloudfront
from cl.lib.models import THUMBNAIL_STATUSES
from cl.lib.redis_utils import get_redis_interface
from cl.search.models import Opinion
from cl.search.selectors import get_total_estimate_count


def get_redis_stat_sum(key_pattern: str, days: int = 10) -> int:
    """Get sum of a stat from Redis for the last N days.

    Args:
        key_pattern: Redis key pattern with {date} placeholder
                    (e.g., "alerts.sent.{date}", "api:v4.d:{date}.count")
        days: Number of days to look back (default: 10)

    Returns:
        Sum of the stat values across all days
    """
    r = get_redis_interface("STATS")
    keys = []
    for x in range(0, days):
        d = (now().date() - timedelta(days=x)).isoformat()
        keys.append(key_pattern.format(date=d))
    return sum(int(result) for result in r.mget(*keys) if result is not None)


@cache_memoize(5 * 60)
def get_v2_homepage_stats():
    """
    Get all stats displayed in the new homepage and return them as a dict.
    """
    ten_days_ago = make_aware(datetime.today() - timedelta(days=10), UTC)

    # Get stats from Redis (new system)
    alerts_in_last_ten = get_redis_stat_sum("alerts.sent.{date}")
    queries_in_last_ten = get_redis_stat_sum("search.results.{date}")
    api_in_last_ten = get_redis_stat_sum("api:v4.d:{date}.count")

    # Let the DB calculate total minutes and default to 0 if no rows exist
    minutes_of_oa = Audio.objects.aggregate(
        minutes=Floor(Coalesce(Sum("duration"), Value(0)) / Value(60.0))
    )["minutes"]

    homepage_stats = {
        "alerts_in_last_ten": alerts_in_last_ten,
        "queries_in_last_ten": queries_in_last_ten,
        "api_in_last_ten": api_in_last_ten,
        "minutes_of_oa": int(minutes_of_oa),
        "opinion_count": get_total_estimate_count("search_opinion"),
        "docket_count": get_total_estimate_count("search_docket"),
        "recap_doc_count": get_total_estimate_count("search_recapdocument"),
    }
    return homepage_stats


@cache_memoize(5 * 60)
def get_homepage_stats():
    """Get any stats that are displayed on the homepage and return them as a
    dict
    """
    ten_days_ago = make_aware(datetime.today() - timedelta(days=10), UTC)

    # Get stats from Redis
    alerts_in_last_ten = get_redis_stat_sum("alerts.sent.{date}")
    queries_in_last_ten = get_redis_stat_sum("search.results.{date}")
    api_in_last_ten = get_redis_stat_sum("api:v4.d:{date}.count")

    # Get stats from database
    opinions_in_last_ten = Opinion.objects.filter(
        date_created__gte=ten_days_ago
    ).count()
    oral_arguments_in_last_ten = Audio.objects.filter(
        date_created__gte=ten_days_ago
    ).count()

    homepage_data = {
        "alerts_in_last_ten": alerts_in_last_ten,
        "queries_in_last_ten": queries_in_last_ten,
        "api_in_last_ten": api_in_last_ten,
        "opinions_in_last_ten": opinions_in_last_ten,
        "oral_arguments_in_last_ten": oral_arguments_in_last_ten,
        "users_in_last_ten": User.objects.filter(
            date_joined__gte=ten_days_ago
        ).count(),
        "days_of_oa": naturalduration(
            Audio.objects.aggregate(Sum("duration"))["duration__sum"],
            as_dict=True,
        )["d"],
        "private": False,  # VERY IMPORTANT!
    }
    return homepage_data


def delete_from_ia(url: str) -> Response:
    """Delete an item from Internet Archive by URL

    :param url: The URL of the item, for example,
    https://archive.org/download/gov.uscourts.nyed.299029/gov.uscourts.nyed.299029.30.0.pdf
    :return: The requests.Response of the request to IA.
    """
    # Get the path and drop the /download/ part of it to just get the bucket
    # and the path
    path = parse.urlparse(url).path
    bucket_path = path.split("/", 2)[2]
    storage_domain = "https://s3.us.archive.org"
    return requests.delete(
        f"{storage_domain}/{bucket_path}",
        headers={
            "Authorization": f"LOW {settings.IA_ACCESS_KEY}:{settings.IA_SECRET_KEY}",
            "x-archive-cascade-delete": "1",
        },
        timeout=60,
    )


def seal_documents(queryset: QuerySet) -> list[str]:
    """Delete a queryset of RECAPDocuments and mark them as sealed.

    :param queryset: A queryset of RECAPDocuments you wish to seal.
    :return: a list of URLs that did not succeed or an empty list if everything
    worked well.
    """
    ia_failures = []
    deleted_filepaths = []
    for rd in queryset:
        # Thumbnail
        if rd.thumbnail:
            deleted_filepaths.append(rd.thumbnail.name)
            rd.thumbnail.delete()

        # PDF
        if rd.filepath_local:
            deleted_filepaths.append(rd.filepath_local.name)
            rd.filepath_local.delete()

        # Internet Archive
        if rd.filepath_ia:
            url = rd.filepath_ia
            r = delete_from_ia(url)
            if not r.ok:
                ia_failures.append(url)

        # Clean up other fields and call save()
        # Important to use save() to ensure these changes are updated in ES
        rd.date_upload = None
        rd.is_available = False
        rd.is_sealed = True
        rd.sha1 = ""
        rd.page_count = None
        rd.file_size = None
        rd.ia_upload_failure_count = None
        rd.filepath_ia = ""
        rd.thumbnail_status = THUMBNAIL_STATUSES.NEEDED
        rd.plain_text = ""
        rd.ocr_status = None
        rd.save()

    # Do a CloudFront invalidation
    invalidate_cloudfront([f"/{path}" for path in deleted_filepaths])

    return ia_failures
