import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from http import HTTPStatus
from typing import TypedDict, cast

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import QuerySet, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from cl.alerts.utils import get_alert_estimation_count
from cl.api.utils import (
    ApiUsageRateThrottle,
    get_current_throttle_usage,
    get_user_api_usage,
)
from cl.audio.models import Audio
from cl.custom_filters.templatetags.partition_util import columns
from cl.donate.models import NeonMembership, NeonMembershipLevel
from cl.favorites.models import Prayer
from cl.favorites.utils import get_lifetime_prayer_stats
from cl.lib.elasticsearch_utils import get_court_opinions_counts
from cl.lib.url_utils import BASE_URL
from cl.people_db.models import Person
from cl.search.documents import (
    OpinionClusterDocument,
)
from cl.search.exception import ElasticBadRequestError, ElasticServerError
from cl.search.models import Citation, Court, OpinionCluster
from cl.search.utils import get_redis_stat_sum
from cl.simple_pages.views import get_coverage_data_fds
from cl.stats.constants import StatMetric

logger = logging.getLogger(__name__)


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


async def make_rss_feed_markdown(
    courts: QuerySet,
    jurisdictions: list[str],
    include_entry_types: bool = False,
) -> str:
    """Render PACER courts grouped by jurisdiction as wiki-ready markdown.

    :param courts: The courts to render.
    :param jurisdictions: Jurisdictions to include, in display order. Courts
        in other jurisdictions are omitted.
    :param include_entry_types: If True, render a table showing each court's
        RSS entry types; otherwise render court names in a two-column table
        that reads top to bottom, then left to right.
    :return: A markdown string with one section per jurisdiction.
    """
    jurisdiction_labels = {
        Court.FEDERAL_APPELLATE: "Appellate Courts",
        Court.FEDERAL_DISTRICT: "District Courts",
        Court.FEDERAL_BANKRUPTCY: "Bankruptcy Courts",
    }
    groups: dict[str, list[Court]] = {}
    async for court in courts:
        groups.setdefault(court.jurisdiction, []).append(court)

    sections = []
    for jurisdiction in jurisdictions:
        group = groups.get(jurisdiction)
        if not group:
            continue
        if include_entry_types:
            lines = ["| Court | Docket Entry Types |", "|---|---|"]
            for court in group:
                entry_types = court.pacer_rss_entry_types.replace("|", " ")
                lines.append(f"| {court.short_name} | {entry_types} |")
            body = "\n".join(lines)
        else:
            names = [court.short_name for court in group]
            lines = ["| | |", "|---|---|"]
            for row in columns(names, 2):
                left = row[0]
                right = row[1] if len(row) > 1 else ""
                lines.append(f"| {left} | {right} |")
            body = "\n".join(lines)
        sections.append(f"# {jurisdiction_labels[jurisdiction]}\n\n{body}")
    return "\n\n".join(sections)


async def make_court_link_list(courts: QuerySet, url_name: str) -> str:
    """Render courts as a markdown list of links for the wiki.

    :param courts: The courts to render.
    :param url_name: The URL name to reverse for each court's link. It must
        take a single "court" kwarg.
    :return: A markdown bullet list linking each court.
    """
    lines = []
    async for court in courts:
        url = BASE_URL + reverse(url_name, kwargs={"court": court.pk})
        lines.append(f"- [{court.full_name}]({url})")
    return "\n".join(lines)


async def get_or_build_wiki_json(
    request: HttpRequest,
    cache_key: str,
    build_data: Callable[[bool], Awaitable[dict]],
) -> JsonResponse:
    """Serve a cached JSON payload for the wiki, rebuilding it on request.

    Shared by the wiki-data endpoints so each one only has to describe how
    to build its own payload, not how to cache it.

    Staff users can pass ?bust_cache to skip the cached response and rebuild
    it, e.g. after the underlying data changes. The rebuild is expensive, so
    the param is ignored for everybody else. The flag is also passed to
    build_data() so it can bust any caches of its own nested in the data it
    fetches — otherwise a "fresh" rebuild here could still return
    data that's stale by as much as those inner caches' own TTLs.

    :param request: The request. Only used to check for ?bust_cache + staff.
    :param cache_key: The cache key this payload is stored under.
    :param build_data: An async callable that computes a fresh payload. It
        receives the bust_cache flag so it can propagate it to any caches
        of its own.
    :return: The cached or freshly-built payload as a JsonResponse.
    """
    bust_cache = (
        "bust_cache" in request.GET and (await request.auser()).is_staff  # type: ignore[attr-defined]
    )
    if not bust_cache:
        data = await cache.aget(cache_key)
        if data is not None:
            return JsonResponse(data)

    data = await build_data(bust_cache)
    one_day = 60 * 60 * 24
    await cache.aset(cache_key, data, one_day)
    return JsonResponse(data)


async def wiki_data(request: HttpRequest) -> JsonResponse:
    """Provide data for the external wiki's help pages.

    Returns counts and settings used across several API documentation pages
    so the wiki can display them via external data connectors.

    Staff users can pass ?bust_cache to skip the cached response and rebuild
    it, e.g. after court metadata changes. The rebuild is expensive, so the
    param is ignored for everybody else.
    """
    return await get_or_build_wiki_json(request, "wiki-data", build_wiki_data)


async def build_wiki_data(bust_cache: bool = False) -> dict:
    """Build the payload served by wiki_data().

    Kept separate from the view so get_or_build_wiki_json() can call it only
    when the cached payload is missing or busted.

    :param bust_cache: Passed through to nested caches (e.g. financial
        disclosure counts) so busting this endpoint's cache doesn't leave
        stale data behind in those.
    :return: The wiki-data payload.
    """
    court_count = await Court.objects.exclude(
        jurisdiction=Court.TESTING_COURT
    ).acount()
    citation_count = await Citation.objects.acount()

    rate = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["citations"]  # type: ignore[misc]
    count, period = parse_throttle_rate_for_template(rate)  # type: ignore[misc]

    fd_data = await get_coverage_data_fds(bust_cache=bust_cache)
    # Yesterday's alert total; start=1 skips today's still-filling bucket.
    alerts_sent_count = await sync_to_async(get_redis_stat_sum)(
        f"{StatMetric.ALERTS_SENT}.{{date}}", days=1, start=1
    )

    # PACER RSS feed coverage, pre-rendered as markdown for the alerts help
    # page. The full-feed section omits appellate courts to match the old
    # /help/alerts page, which only listed district and bankruptcy courts.
    pacer_courts = Court.federal_courts.all_pacer_courts()
    district_and_bankruptcy = [
        Court.FEDERAL_DISTRICT,
        Court.FEDERAL_BANKRUPTCY,
    ]
    all_jurisdictions = [Court.FEDERAL_APPELLATE, *district_and_bankruptcy]
    rss_feeds = {
        "full": await make_rss_feed_markdown(
            pacer_courts.filter(
                pacer_has_rss_feed=True, pacer_rss_entry_types="all"
            ),
            district_and_bankruptcy,
        ),
        "partial": await make_rss_feed_markdown(
            pacer_courts.filter(pacer_has_rss_feed=True).exclude(
                pacer_rss_entry_types="all"
            ),
            all_jurisdictions,
            include_entry_types=True,
        ),
        "none": await make_rss_feed_markdown(
            pacer_courts.filter(pacer_has_rss_feed=False),
            all_jurisdictions,
        ),
    }
    prayer_stats = await get_lifetime_prayer_stats(Prayer.GRANTED)

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
        "alerts": {
            "max_free_docket_alerts": settings.MAX_FREE_DOCKET_ALERTS,  # type: ignore[misc]
            "docket_alert_recap_bonus": settings.DOCKET_ALERT_RECAP_BONUS,  # type: ignore[misc]
            "rt_alerts_sending_rate": int(
                settings.REAL_TIME_ALERTS_SENDING_RATE / 60  # type: ignore[misc]
            ),
            "max_attorneys_to_percolate": settings.MAX_ATTORNEYS_TO_PERCOLATE,  # type: ignore[misc]
        },
        "rss_feeds": rss_feeds,
        "prayers": {
            "daily_quota": settings.ALLOWED_PRAYER_COUNT,  # type: ignore[misc]
            "member_daily_quota": settings.ALLOWED_PRAYER_COUNT * 3,  # type: ignore[misc]
            "granted_count": prayer_stats.prayer_count,
            "distinct_users": prayer_stats.distinct_users,
            "distinct_documents": prayer_stats.distinct_count,
            "total_cost": prayer_stats.total_cost,
        },
        "feeds": {
            "opinion_courts": await make_court_link_list(
                Court.objects.filter(in_use=True, has_opinion_scraper=True),
                "jurisdiction_feed",
            ),
        },
        "podcasts": {
            "oral_argument_courts": await make_court_link_list(
                Court.objects.filter(
                    in_use=True, has_oral_argument_scraper=True
                ),
                "jurisdiction_podcast",
            ),
        },
    }
    return data


async def wiki_coverage_data(request: HttpRequest) -> JsonResponse:
    """Provide data for the external wiki's coverage help pages.

    Returns counts used across the coverage help pages so the wiki can
    display them via external data connectors. This is kept separate from
    wiki_data() so that endpoint doesn't keep growing without bound — new
    coverage stats belong here instead.

    Staff users can pass ?bust_cache to skip the cached response and rebuild
    it, e.g. after new financial disclosures land. The rebuild is expensive,
    so the param is ignored for everybody else.
    """
    return await get_or_build_wiki_json(
        request, "wiki-coverage-data", build_wiki_coverage_data
    )


async def build_wiki_coverage_data(bust_cache: bool = False) -> dict:
    """Build the payload served by wiki_coverage_data().

    Kept separate from the view so get_or_build_wiki_json() can call it only
    when the cached payload is missing or busted.

    :param bust_cache: Passed through to get_coverage_data_fds() so busting
        this endpoint's cache actually refreshes the financial disclosure
        counts too, instead of leaving up to a week-old counts from that
        function's own cache in place.
    :return: The wiki-coverage-data payload.
    """
    fd_data = await get_coverage_data_fds(bust_cache=bust_cache)
    judge_count = await Person.objects.all().acount()

    oa_aggregate = await Audio.objects.aaggregate(Sum("duration"))
    oa_duration = oa_aggregate["duration__sum"]
    if oa_duration:
        # Round to the nearest minute — the wiki renders this value as-is,
        # so it can't do any rounding of its own.
        oa_duration = round(oa_duration / 60)

    return {
        "judges": {
            "count": judge_count,
        },
        "oral_arguments": {
            "duration_minutes": oa_duration,
        },
        "financial_disclosures": {
            "disclosures": fd_data["disclosures"],
            "investments": fd_data["investments"],
            "positions": fd_data["positions"],
            "agreements": fd_data["agreements"],
            "non_investment_income": fd_data["non_investment_income"],
            "spousal_income": fd_data["spousal_income"],
            "reimbursements": fd_data["reimbursements"],
            "gifts": fd_data["gifts"],
            "debts": fd_data["debts"],
        },
    }


class MembershipInfo(TypedDict):
    """Membership level + active status."""

    level: str
    is_active: bool


class ApiUsageViewSet(ViewSet):
    """Provides the authenticated user's API usage and rate limits.

    Returns current throttle usage, 14-day historical usage, and membership
    information.

    This endpoint uses its own dedicated ``api_usage`` throttle scope, which is
    deliberately kept separate from the main API quota. That isolation serves
    two purposes: monitoring your usage never consumes the quota being
    monitored, and a user who has exhausted their API quota elsewhere can still
    reach this endpoint to inspect their usage and ``reset_at`` — exactly when
    that information is most useful. The ``api_usage`` scope carries a generous
    limit of its own only to keep the endpoint from being abused; that limit is
    reported alongside the others in the ``current_usage`` list.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ApiUsageRateThrottle]
    pagination_class = None

    def _get_historical_usage(self, user: User) -> dict[str, int]:
        """14-day daily request counts from Redis."""
        today = datetime.today()
        return get_user_api_usage(user.pk, today - timedelta(days=14), today)

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
                "current_usage": get_current_throttle_usage(user),
                "historical_usage": self._get_historical_usage(user),
                "membership": self._get_membership(user),
            }
        )
