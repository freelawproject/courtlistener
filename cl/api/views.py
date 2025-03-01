import logging
import re
from datetime import date
from http import HTTPStatus
from typing import Optional

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.core.cache import cache
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import aget_object_or_404  # type: ignore[attr-defined]
from django.template.response import TemplateResponse
from django.views.decorators.cache import cache_page
from django.views.generic import TemplateView
from requests import Session

from cl.lib.elasticsearch_utils import (
    do_es_alert_estimation_query,
    get_court_opinions_counts,
    get_opinions_coverage_over_time,
)
from cl.search.documents import (
    AudioDocument,
    DocketDocument,
    OpinionClusterDocument,
)
from cl.search.forms import SearchForm
from cl.search.models import SEARCH_TYPES, Citation, Court, OpinionCluster
from cl.simple_pages.coverage_utils import build_chart_data
from cl.simple_pages.views import get_coverage_data_fds

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
            cache_key, court_counts, timeout=settings.QUERY_RESULTS_CACHE  # type: ignore
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


async def rest_docs(request, version=None):
    """Show the correct version of the rest docs.

    Latest version is shown when not specified in args.
    """
    court_count = await Court.objects.acount()
    latest = version is None
    context = {"court_count": court_count, "private": not latest}
    return TemplateResponse(
        request,
        [f"rest-docs-{version}.html", "rest-docs-vlatest.html"],
        context,
    )


async def api_index(request: HttpRequest) -> HttpResponse:
    court_count = await Court.objects.exclude(
        jurisdiction=Court.TESTING_COURT
    ).acount()
    return TemplateResponse(
        request, "docs.html", {"court_count": court_count, "private": False}
    )


async def bulk_data_index(request: HttpRequest) -> HttpResponse:
    """Shows an index page for the dumps."""
    disclosure_coverage = await get_coverage_data_fds()
    return TemplateResponse(
        request,
        "bulk-data.html",
        disclosure_coverage,
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


async def citation_lookup_api(
    request: HttpRequest, version=None
) -> HttpResponse:

    cite_count = await Citation.objects.acount()
    rate = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["citations"]  # type: ignore
    default_throttle_rate = parse_throttle_rate_for_template(rate)
    custom_throttle_rate = None
    if request.user and request.user.is_authenticated:
        rate = settings.REST_FRAMEWORK[  # type: ignore
            "CITATION_LOOKUP_OVERRIDE_THROTTLE_RATES"
        ].get(request.user.username, None)
        custom_throttle_rate = parse_throttle_rate_for_template(rate)

    return TemplateResponse(
        request,
        [
            f"citation-lookup-api-{version}.html",
            "citation-lookup-api-vlatest.html",
        ],
        {
            "cite_count": cite_count,
            "default_throttle_rate": default_throttle_rate,
            "custom_throttle_rate": custom_throttle_rate,
            "max_citation_per_request": settings.MAX_CITATIONS_PER_REQUEST,  # type: ignore
            "private": False,
            "version": version if version else "v4",
        },
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
) -> tuple[Optional[date], Optional[date]]:
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

    search_form = await sync_to_async(SearchForm)(request.GET.copy())
    if not search_form.is_valid():
        return JsonResponse(
            {"error": "Invalid SearchForm"},
            safe=True,
            status=HTTPStatus.BAD_REQUEST,
        )
    cd = search_form.cleaned_data
    search_type = cd["type"]
    match search_type:
        case SEARCH_TYPES.ORAL_ARGUMENT:
            # Elasticsearch version for OA
            search_query = AudioDocument.search()
            total_query_results = await sync_to_async(
                do_es_alert_estimation_query
            )(search_query, cd, day_count)
        case SEARCH_TYPES.OPINION:
            # Elasticsearch version for O
            search_query = OpinionClusterDocument.search()
            total_query_results = await sync_to_async(
                do_es_alert_estimation_query
            )(search_query, cd, day_count)
        case SEARCH_TYPES.RECAP:
            # Elasticsearch version for RECAP
            search_query = DocketDocument.search()
            total_query_results = await sync_to_async(
                do_es_alert_estimation_query
            )(search_query, cd, day_count)
        case _:
            total_query_results = 0
    return JsonResponse({"count": total_query_results}, safe=True)


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


async def webhooks_docs(request, version=None):
    """Show the correct version of the webhooks docs"""

    context = {"private": False}
    return TemplateResponse(
        request,
        [f"webhooks-docs-{version}.html", "webhooks-docs-vlatest.html"],
        context,
    )


class VersionedTemplateView(TemplateView):
    """Custom template view to handle the right template based on the path
    version requested.
    """

    def get_template_names(self):
        version = self.kwargs.get("version", "vlatest")
        base_template = self.template_name.replace("-vlatest", f"-{version}")
        return [base_template, self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["version"] = self.kwargs.get("version", "v4")
        return context
