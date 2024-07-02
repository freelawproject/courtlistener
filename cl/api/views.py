import logging
from datetime import date
from http import HTTPStatus
from typing import Optional

import waffle
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import aget_object_or_404  # type: ignore[attr-defined]
from django.template.response import TemplateResponse
from django.views.decorators.cache import cache_page
from requests import Session

from cl.lib.elasticsearch_utils import do_es_alert_estimation_query
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import (
    build_alert_estimation_query,
    build_court_count_query,
    build_coverage_query,
    get_solr_interface,
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


async def annotate_courts_with_counts(courts, court_count_tuples):
    """Solr gives us a response like:

        court_count_tuples = [
            ('ca2', 200),
            ('ca1', 42),
            ...
        ]

    Here we add an attribute to our court objects so they have these values.
    """
    # Convert the tuple to a dict
    court_count_dict = {}
    for court_str, count in court_count_tuples:
        court_count_dict[court_str] = count

    async for court in courts:
        court.count = court_count_dict.get(court.pk, 0)

    return courts


async def make_court_variable():
    courts = Court.objects.exclude(jurisdiction=Court.TESTING_COURT)

    @sync_to_async
    def court_count_query():
        with Session() as session:
            si = ExtraSolrInterface(
                settings.SOLR_OPINION_URL, http_connection=session, mode="r"
            )
            return si.query().add_extra(**build_court_count_query()).execute()

    response = await court_count_query()
    court_count_tuples = response.facet_counts.facet_fields["court_exact"]
    courts = await annotate_courts_with_counts(courts, court_count_tuples)
    return courts


async def court_index(request: HttpRequest) -> HttpResponse:
    """Shows the information we have available for the courts."""
    courts = await make_court_variable()
    return TemplateResponse(
        request, "jurisdictions.html", {"courts": courts, "private": False}
    )


async def rest_docs(request, version=None):
    """Show the correct version of the rest docs"""
    courts = []  # await make_court_variable()
    court_count = len(courts)
    context = {"court_count": court_count, "courts": courts, "private": False}
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


async def citation_lookup_api(request: HttpRequest) -> HttpResponse:
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
        "citation-lookup-api.html",
        {
            "cite_count": cite_count,
            "default_throttle_rate": default_throttle_rate,
            "custom_throttle_rate": custom_throttle_rate,
            "max_citation_per_request": settings.MAX_CITATIONS_PER_REQUEST,  # type: ignore
            "private": False,
        },
    )


def strip_zero_years(data):
    """Removes zeroes from the ends of the court data

    Some courts only have values through to a certain date, but we don't
    check for that in our queries. Instead, we truncate any zero-values that
    occur at the end of their stats.
    """
    start = 0
    end = len(data)
    # Slice off zeroes at the beginning
    for i, data_pair in enumerate(data):
        if data_pair[1] != 0:
            start = i
            break

    # Slice off zeroes at the end
    for i, data_pair in reversed(list(enumerate(data))):
        if data_pair[1] != 0:
            end = i
            break

    return data[start : end + 1]


async def coverage_data(request, version, court):
    """Provides coverage data for a court.

    Responds to either AJAX or regular requests.
    """

    if court != "all":
        court_str = (await aget_object_or_404(Court, pk=court)).pk
    else:
        court_str = "all"
    q = request.GET.get("q")

    @sync_to_async
    def query_facets(c_str, q_str):
        with Session() as session:
            si = ExtraSolrInterface(
                settings.SOLR_OPINION_URL, http_connection=session, mode="r"
            )
            facet_field = "dateFiled"
            return facet_field, (
                si.query()
                .add_extra(**build_coverage_query(c_str, q_str, facet_field))
                .execute()
            )

    facet_field, response = await query_facets(court_str, q)
    counts = response.facet_counts.facet_ranges[facet_field]["counts"]
    counts = strip_zero_years(counts)

    # Calculate the totals
    annual_counts = {}
    total_docs = 0
    for date_string, count in counts:
        annual_counts[date_string[:4]] = count
        total_docs += count

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
    chart_data = []
    if request.method == "GET":
        court_ids = request.GET.get("court_ids").split(",")  # type: ignore
        chart_data = await sync_to_async(build_chart_data)(court_ids)
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

    es_flag_for_oa = await sync_to_async(waffle.flag_is_active)(
        request, "oa-es-active"
    )
    es_flag_for_o = await sync_to_async(waffle.flag_is_active)(
        request, "o-es-active"
    )
    es_flag_for_r = await sync_to_async(waffle.flag_is_active)(
        request, "recap-alerts-active"
    )
    is_es_form = es_flag_for_oa or es_flag_for_o or es_flag_for_r
    search_form = await sync_to_async(SearchForm)(
        request.GET.copy(), is_es_form=is_es_form
    )
    if not search_form.is_valid():
        return JsonResponse(
            {"error": "Invalid SearchForm"},
            safe=True,
            status=HTTPStatus.BAD_REQUEST,
        )
    cd = search_form.cleaned_data
    search_type = cd["type"]
    match search_type:
        case SEARCH_TYPES.ORAL_ARGUMENT if es_flag_for_oa:
            # Elasticsearch version for OA
            search_query = AudioDocument.search()
            total_query_results = await sync_to_async(
                do_es_alert_estimation_query
            )(search_query, cd, day_count)
        case SEARCH_TYPES.OPINION if es_flag_for_o:
            # Elasticsearch version for O
            search_query = OpinionClusterDocument.search()
            total_query_results = await sync_to_async(
                do_es_alert_estimation_query
            )(search_query, cd, day_count)
        case SEARCH_TYPES.RECAP if es_flag_for_r:
            # Elasticsearch version for RECAP
            search_query = DocketDocument.search()
            total_query_results = await sync_to_async(
                do_es_alert_estimation_query
            )(search_query, cd, day_count)
        case _:

            @sync_to_async
            def get_total_query_results(cleaned_data, dc):
                with Session() as session:
                    try:
                        si = get_solr_interface(
                            cleaned_data, http_connection=session
                        )
                    except NotImplementedError:
                        logger.error(
                            "Tried getting solr connection for %s, but it's not "
                            "implemented yet",
                            cleaned_data["type"],
                        )
                        raise
                    extra = build_alert_estimation_query(cleaned_data, int(dc))
                    response = si.query().add_extra(**extra).execute()
                    return response.result.numFound

            total_query_results = await get_total_query_results(cd, day_count)
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
