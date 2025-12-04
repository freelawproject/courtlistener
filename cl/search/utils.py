from datetime import UTC, date, datetime, timedelta

from cache_memoize import cache_memoize
from django.contrib.auth.models import User
from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce, Floor
from django.utils.timezone import make_aware, now

from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import naturalduration
from cl.lib.redis_utils import get_redis_interface
from cl.search.models import Opinion
from cl.search.selectors import get_total_estimate_count
from cl.stats.models import Stat
from cl.visualizations.models import SCOTUSMap


@cache_memoize(5 * 60)
def get_v2_homepage_stats():
    """
    Get all stats displayed in the new homepage and return them as a dict.
    """
    ten_days_ago = make_aware(datetime.today() - timedelta(days=10), UTC)
    last_ten_days = [
        f"api:v3.d:{(date.today() - timedelta(days=x)).isoformat()}.count"
        for x in range(0, 10)
    ]

    # Get stats from Redis (new system)
    r = get_redis_interface("STATS")

    # Build Redis keys for last 10 days using timezone-aware dates
    alert_keys = []
    query_keys = []
    for x in range(0, 10):
        d = (now().date() - timedelta(days=x)).isoformat()
        alert_keys.append(f"alerts.sent.{d}")
        query_keys.append(f"search.results.{d}")

    alerts_in_last_ten = sum(
        int(result) for result in r.mget(*alert_keys) if result is not None
    )
    queries_in_last_ten = sum(
        int(result) for result in r.mget(*query_keys) if result is not None
    )
    api_in_last_ten = sum(
        [
            int(result)
            for result in r.mget(*last_ten_days)
            if result is not None
        ]
    )

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
    r = get_redis_interface("STATS")
    ten_days_ago = make_aware(datetime.today() - timedelta(days=10), UTC)
    last_ten_days = [
        f"api:v3.d:{(date.today() - timedelta(days=x)).isoformat()}.count"
        for x in range(0, 10)
    ]

    # Build Redis keys for last 10 days using timezone-aware dates
    alert_keys = []
    query_keys = []
    for x in range(0, 10):
        d = (now().date() - timedelta(days=x)).isoformat()
        alert_keys.append(f"alerts.sent.{d}")
        query_keys.append(f"search.results.{d}")

    homepage_data = {
        "alerts_in_last_ten": sum(
            int(result) for result in r.mget(*alert_keys) if result is not None
        ),
        "queries_in_last_ten": sum(
            int(result) for result in r.mget(*query_keys) if result is not None
        ),
        "opinions_in_last_ten": Opinion.objects.filter(
            date_created__gte=ten_days_ago
        ).count(),
        "oral_arguments_in_last_ten": Audio.objects.filter(
            date_created__gte=ten_days_ago
        ).count(),
        "api_in_last_ten": sum(
            [
                int(result)
                for result in r.mget(*last_ten_days)
                if result is not None
            ]
        ),
        "users_in_last_ten": User.objects.filter(
            date_joined__gte=ten_days_ago
        ).count(),
        "days_of_oa": naturalduration(
            Audio.objects.aggregate(Sum("duration"))["duration__sum"],
            as_dict=True,
        )["d"],
        "viz_in_last_ten": SCOTUSMap.objects.filter(
            date_published__gte=ten_days_ago, published=True
        ).count(),
        "visualizations": SCOTUSMap.objects.filter(
            published=True, deleted=False
        )
        .annotate(Count("clusters"))
        .filter(
            # Ensures that we only show good stuff on homepage
            clusters__count__gt=10,
        )
        .order_by("-date_published", "-date_modified", "-date_created")[:1],
        "private": False,  # VERY IMPORTANT!
    }
    return homepage_data
