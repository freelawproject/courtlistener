from datetime import UTC, date, datetime, timedelta

from cache_memoize import cache_memoize
from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.utils.timezone import make_aware

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

    alerts_in_last_ten = (
        Stat.objects.filter(
            name__contains="alerts.sent", date_logged__gte=ten_days_ago
        ).aggregate(Sum("count"))["count__sum"]
        or 0
    )

    queries_in_last_ten = (
        Stat.objects.filter(
            name="search.results", date_logged__gte=ten_days_ago
        ).aggregate(Sum("count"))["count__sum"]
        or 0
    )

    r = get_redis_interface("STATS")
    api_in_last_ten = sum(
        [
            int(result)
            for result in r.mget(*last_ten_days)
            if result is not None
        ]
    )

    minutes_of_oa = (
        Audio.objects.aggregate(Sum("duration"))["duration__sum"] or 0 // 60
    )

    homepage_stats = {
        "alerts_in_last_ten": alerts_in_last_ten,
        "queries_in_last_ten": queries_in_last_ten,
        "api_in_last_ten": api_in_last_ten,
        "minutes_of_oa": minutes_of_oa,
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
    homepage_data = {
        "alerts_in_last_ten": Stat.objects.filter(
            name__contains="alerts.sent", date_logged__gte=ten_days_ago
        ).aggregate(Sum("count"))["count__sum"],
        "queries_in_last_ten": Stat.objects.filter(
            name="search.results", date_logged__gte=ten_days_ago
        ).aggregate(Sum("count"))["count__sum"],
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
