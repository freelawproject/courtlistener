import logging
import re
import time
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import TypedDict, cast

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import aget_object_or_404  # type: ignore[attr-defined]
from django.template.response import TemplateResponse
from django.views.decorators.cache import cache_page
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from cl.alerts.utils import get_alert_estimation_count
from cl.api.models import APIThrottle, ThrottleType
from cl.api.utils import invert_user_logs
from cl.donate.models import NeonMembership, NeonMembershipLevel
from cl.lib.elasticsearch_utils import (
    get_court_opinions_counts,
    get_opinions_coverage_over_time,
)
from cl.lib.ratelimiter import parse_rate
from cl.search.documents import (
    OpinionClusterDocument,
)
from cl.search.exception import ElasticBadRequestError, ElasticServerError
from cl.search.models import Citation, Court, OpinionCluster
from cl.search.utils import get_redis_stat_sum
from cl.simple_pages.coverage_utils import build_chart_data
from cl.simple_pages.views import get_coverage_data_fds
from cl.stats.constants import StatMetric

logger = logging.getLogger(__name__)

max_court_id_length = Court._meta.get_field("id").max_length
VALID_COURT_ID_REGEX = re.compile(rf"^\w{{1,{max_court_id_length}}}$")


async def get_cached_court_counts(courts_queryset: QuerySet) -> dict[str, int]:
    """Fetch court counts from cache or ES if not available.
    :return: A dict mapping court IDs to their respective counts of
    opinions, or None if no counts are available.
    """

    cache_key = "court_counts_o"
    court_counts = cache.get(cache_key)
    if court_counts:
        return court_counts

    courts_count = await courts_queryset.acount()
    court_counts = await sync_to_async(get_court_opinions_counts)(
        OpinionClusterDocument.search(), courts_count
    )
    if court_counts:
        cache.set(
            cache_key,
            court_counts,
            timeout=settings.QUERY_RESULTS_CACHE,  # type: ignore
        )
    return court_counts or {}


async def make_court_variable() -> QuerySet:
    """
    Create a list of court objects with an added attribute for the count of associated opinions.

    :return: A QuerySet of Court objects with an added `count` attribute reflecting
             the number of associated opinions.
    """

    courts = Court.objects.exclude(jurisdiction=Court.TESTING_COURT)
    courts_counts = await get_cached_court_counts(courts)
    # Add the count attribute to courts.
    async for court in courts:
        court.count = courts_counts.get(court.pk, 0)
    return courts


async def court_index(request: HttpRequest) -> HttpResponse:
    """Shows the information we have available for the courts."""
    courts = await make_court_variable()
    return TemplateResponse(
        request, "jurisdictions.html", {"courts": courts, "private": False}
    )


async def coverage_data(request, version, court):
    """Provides coverage data for a court.

    Responds to either AJAX or regular requests.
    """

    if court != "all":
        court_str = (await aget_object_or_404(Court, pk=court)).pk
    else:
        court_str = "all"
    q = request.GET.get("q")
    opinions_coverage = await sync_to_async(get_opinions_coverage_over_time)(
        OpinionClusterDocument.search(), court_str, q, "dateFiled"
    )
    # Calculate the totals
    annual_counts = {}
    total_docs = 0
    for year_coverage in opinions_coverage:
        annual_counts[year_coverage["key_as_string"]] = year_coverage[
            "doc_count"
        ]
        total_docs += year_coverage["doc_count"]

    return JsonResponse(
        {"annual_counts": annual_counts, "total": total_docs}, safe=True
    )


async def fetch_first_last_date_filed(
    court_id: str,
) -> tuple[date | None, date | None]:
    """Fetch first and last date for court

    :param court_id: Court object id
    :return: First/last date filed, if any
    """
    query = OpinionCluster.objects.filter(docket__court=court_id).order_by(
        "date_filed"
    )
    first, last = await query.afirst(), await query.alast()
    if first:
        return first.date_filed, last.date_filed
    return None, None


@sync_to_async
@cache_page(7 * 60 * 60 * 24, key_prefix="coverage")
@async_to_sync
async def coverage_data_opinions(request: HttpRequest):
    """Generate Coverage Chart Data

    Accept GET to query court data for timelines-chart on coverage page

    :param request: The HTTP request
    :return: Timeline data for court(s)
    """

    if request.method != "GET":
        return JsonResponse([], safe=False)

    court_ids = request.GET.get("court_ids", "").strip()  # type: ignore
    if not court_ids:
        return JsonResponse([], safe=False)

    # Clean and validate court_ids
    valid_court_ids = [
        court_id.strip()
        for court_id in court_ids.split(",")
        if court_id.strip() and VALID_COURT_ID_REGEX.match(court_id.strip())
    ]
    if not valid_court_ids:
        return JsonResponse([], safe=False)

    chart_data = await sync_to_async(build_chart_data)(valid_court_ids)
    return JsonResponse(chart_data, safe=False)


async def get_result_count(request, version, day_count):
    """Get the count of results for the past `day_count` number of days

    GET parameters will be a complete search string

    :param request: The Django request object
    :param version: The API version number (ignored for now, but there for
    later)
    :param day_count: The number of days to average across. More is slower.
    :return: A JSON object with the number of hits during the last day_range
    period.
    """

    try:
        estimation = await sync_to_async(get_alert_estimation_count)(
            request.GET.copy(), int(day_count)
        )
    except (ElasticServerError, ElasticBadRequestError):
        # The query couldn't be run against Elasticsearch.
        return JsonResponse(
            {
                "error": "Internal server error when trying to get the "
                "estimation count."
            },
            safe=True,
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    if estimation is None:
        return JsonResponse(
            {"error": "Invalid SearchForm"},
            safe=True,
            status=HTTPStatus.BAD_REQUEST,
        )
    total_query_results, total_case_only_query_results = estimation
    return JsonResponse(
        {
            "count": total_query_results,
            "count_case_only": total_case_only_query_results,
        },
        safe=True,
    )


async def deprecated_api(request, v):
    return JsonResponse(
        {
            "meta": {
                "status": "This endpoint is deprecated. Please upgrade to the "
                "newest version of the API.",
            },
            "objects": [],
        },
        safe=False,
        status=HTTPStatus.GONE,
    )


def parse_throttle_rate_for_template(rate: str) -> tuple[int, str] | None:
    """
    Parses a throttle rate string and returns a tuple containing the number of
    citations allowed and the throttling duration in a format suitable for
    templates.

    Args:
        rate (str): A string representing the throttle rate

    Returns:
        A tuple containing a two elements:
            - The number of citations allowed (int).
            - The throttling duration (str).
    """
    if not rate:
        return None
    duration_as_str = {"s": "second", "m": "minute", "h": "hour", "d": "day"}
    num, period = rate.split("/")
    return int(num), duration_as_str[period[0]]


async def wiki_data(request: HttpRequest) -> JsonResponse:
    """Provide data for the external wiki's help pages.

    Returns counts and settings used across several API documentation pages
    so the wiki can display them via external data connectors.
    """
    cache_key = "wiki-data"
    data = await cache.aget(cache_key)
    if data is not None:
        return JsonResponse(data)

    court_count = await Court.objects.exclude(
        jurisdiction=Court.TESTING_COURT
    ).acount()
    citation_count = await Citation.objects.acount()

    rate = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["citations"]  # type: ignore[misc]
    count, period = parse_throttle_rate_for_template(rate)  # type: ignore[misc]

    fd_data = await get_coverage_data_fds()
    # Yesterday's alert total; start=1 skips today's still-filling bucket.
    alerts_sent_count = await sync_to_async(get_redis_stat_sum)(
        f"{StatMetric.ALERTS_SENT}.{{date}}", days=1, start=1
    )

    data = {
        "court_count": court_count,
        "citation_count": citation_count,
        "alerts_sent_count": alerts_sent_count,
        "citation_lookup": {
            "throttle_count": count,
            "throttle_period": period,
            "max_per_request": settings.MAX_CITATIONS_PER_REQUEST,  # type: ignore[misc]
        },
        "financial_disclosures": {
            "disclosures": fd_data["disclosures"],
            "investments": fd_data["investments"],
        },
    }
    one_day = 60 * 60 * 24
    await cache.aset(cache_key, data, one_day)
    return JsonResponse(data)


# Scopes to skip when building current_usage — these aren't relevant
# for authenticated users checking their own limits.
EXCLUDED_THROTTLE_SCOPES = {"anon"}


class CurrentUsageDetails(TypedDict):
    """One row per throttle scope in the current_usage list."""

    scope: str
    rate: str
    requests_made: int
    requests_allowed: int
    requests_remaining: int
    window_duration_seconds: float
    reset_at: str | None
    blocked: bool


class MembershipInfo(TypedDict):
    """Membership level + active status."""

    level: str
    is_active: bool


class ApiUsageViewSet(ViewSet):
    """Provides the authenticated user's API usage and rate limits.

    Returns current-window throttle consumption, 14-day historical usage,
    and membership info.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None

    def _get_current_usage(self, user: User) -> list[CurrentUsageDetails]:
        """Read DRF's throttle cache to build per-scope usage.

        Scopes are derived from DEFAULT_THROTTLE_RATES in settings.
        Overrides are looked up from APIThrottle by scope.
        Results are sorted by utilization descending — the limit
        closest to being hit comes first.
        """
        default_rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]  # type: ignore
        overrides = {
            t.throttle_type: (t.blocked, t.rate)
            for t in APIThrottle.objects.filter(user=user)
        }
        current_time = time.time()
        usage: list[CurrentUsageDetails] = []

        for scope, default_rate in default_rates.items():
            if scope in EXCLUDED_THROTTLE_SCOPES:
                continue

            blocked = False
            rate = default_rate
            throttle_type: ThrottleType | None
            match scope:
                case "user":
                    throttle_type = ThrottleType.API
                case "citations":
                    throttle_type = ThrottleType.CITATION_LOOKUP
                case _:
                    throttle_type = None

            override = overrides.get(throttle_type) if throttle_type else None
            if override is not None:
                blocked, override_rate = override
                if override_rate:
                    rate = override_rate

            num_requests, duration = parse_rate(rate)
            cache_key = f"throttle_{scope}_{user.pk}"
            history = cache.get(cache_key, [])
            valid = [ts for ts in history if ts > current_time - duration]
            requests_made = len(valid)

            # Oldest request in the window determines when the first
            # slot frees up (sliding window).
            reset_at = None
            if valid:
                oldest_ts = valid[-1]  # list is newest-first
                reset_at = datetime.fromtimestamp(
                    oldest_ts + duration, tz=UTC
                ).isoformat()

            usage.append(
                {
                    "scope": scope,
                    "rate": rate,
                    "requests_made": requests_made,
                    "requests_allowed": num_requests,
                    "requests_remaining": max(num_requests - requests_made, 0),
                    "window_duration_seconds": duration,
                    "reset_at": reset_at,
                    "blocked": blocked,
                }
            )

        # Sort by utilization descending — limit closest to being hit first.
        # Blocked entries float to the top (utilization = 1.0).
        usage.sort(
            key=lambda u: (
                1.0
                if u["blocked"]
                else u["requests_made"] / u["requests_allowed"]
            ),
            reverse=True,
        )
        return usage

    def _get_historical_usage(self, user: User) -> dict[str, int]:
        """14-day daily request counts from Redis."""
        start = datetime.today() - timedelta(days=14)
        end = datetime.today()
        data = invert_user_logs(start, end, add_usernames=False)
        return data.get(user.pk, {"total": 0})  # type: ignore[call-overload]

    def _get_membership(self, user: User) -> MembershipInfo | None:
        """Return the user's membership level and active status."""
        try:
            membership = NeonMembership.objects.get(user=user)
        except NeonMembership.DoesNotExist:
            return None
        level_display = dict(NeonMembershipLevel.TYPES).get(
            membership.level, "Unknown"
        )
        return {"level": level_display, "is_active": membership.is_active}

    def list(self, request: Request, *args, **kwargs) -> Response:
        # IsAuthenticated permission class rules out AnonymousUser at runtime.
        user = cast(User, request.user)
        return Response(
            {
                "current_usage": self._get_current_usage(user),
                "historical_usage": self._get_historical_usage(user),
                "membership": self._get_membership(user),
            }
        )
