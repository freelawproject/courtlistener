import logging

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template import TemplateDoesNotExist
from requests import Session
from rest_framework import status
from rest_framework.status import HTTP_400_BAD_REQUEST

from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import (
    build_alert_estimation_query,
    build_court_count_query,
    build_coverage_query,
    get_solr_interface,
)
from cl.search.forms import SearchForm
from cl.search.models import Court
from cl.simple_pages.views import get_coverage_data_fds

logger = logging.getLogger(__name__)


def annotate_courts_with_counts(courts, court_count_tuples):
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

    for court in courts:
        court.count = court_count_dict.get(court.pk, 0)

    return courts


def make_court_variable():
    courts = Court.objects.exclude(jurisdiction=Court.TESTING_COURT)
    with Session() as session:
        si = ExtraSolrInterface(
            settings.SOLR_OPINION_URL, http_connection=session, mode="r"
        )
        response = si.query().add_extra(**build_court_count_query()).execute()
    court_count_tuples = response.facet_counts.facet_fields["court_exact"]
    courts = annotate_courts_with_counts(courts, court_count_tuples)
    return courts


def court_index(request: HttpRequest) -> HttpResponse:
    """Shows the information we have available for the courts."""
    courts = make_court_variable()
    return render(
        request, "jurisdictions.html", {"courts": courts, "private": False}
    )


def rest_docs(request, version=None):
    """Show the correct version of the rest docs"""
    courts = make_court_variable()
    court_count = len(courts)
    context = {"court_count": court_count, "courts": courts, "private": False}
    try:
        return render(request, f"rest-docs-{version}.html", context)
    except TemplateDoesNotExist:
        return render(request, "rest-docs-vlatest.html", context)


def api_index(request: HttpRequest) -> HttpResponse:
    court_count = Court.objects.exclude(
        jurisdiction=Court.TESTING_COURT
    ).count()
    return render(
        request, "docs.html", {"court_count": court_count, "private": False}
    )


def replication_docs(request: HttpRequest) -> HttpResponse:
    return render(request, "replication.html", {"private": False})


def bulk_data_index(request: HttpRequest) -> HttpResponse:
    """Shows an index page for the dumps."""
    disclosure_coverage = get_coverage_data_fds()
    return render(
        request,
        "bulk-data.html",
        disclosure_coverage,
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


def coverage_data(request, version, court):
    """Provides coverage data for a court.

    Responds to either AJAX or regular requests.
    """

    if court != "all":
        court_str = get_object_or_404(Court, pk=court).pk
    else:
        court_str = "all"
    q = request.GET.get("q")
    with Session() as session:
        si = ExtraSolrInterface(
            settings.SOLR_OPINION_URL, http_connection=session, mode="r"
        )
        facet_field = "dateFiled"
        response = (
            si.query()
            .add_extra(**build_coverage_query(court_str, q, facet_field))
            .execute()
        )
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


def get_result_count(request, version, day_count):
    """Get the count of results for the past `day_count` number of days

    GET parameters will be a complete search string

    :param request: The Django request object
    :param version: The API version number (ignored for now, but there for
    later)
    :param day_count: The number of days to average across. More is slower.
    :return: A JSON object with the number of hits during the last day_range
    period.
    """
    search_form = SearchForm(request.GET.copy())
    if not search_form.is_valid():
        return JsonResponse(
            {"error": "Invalid SearchForm"},
            safe=True,
            status=HTTP_400_BAD_REQUEST,
        )

    cd = search_form.cleaned_data
    with Session() as session:
        try:
            si = get_solr_interface(cd, http_connection=session)
        except NotImplementedError:
            logger.error(
                "Tried getting solr connection for %s, but it's not "
                "implemented yet",
                cd["type"],
            )
            raise

        response = (
            si.query()
            .add_extra(**build_alert_estimation_query(cd, int(day_count)))
            .execute()
        )
    return JsonResponse({"count": response.result.numFound}, safe=True)


def deprecated_api(request, v):
    return JsonResponse(
        {
            "meta": {
                "status": "This endpoint is deprecated. Please upgrade to the "
                "newest version of the API.",
            },
            "objects": [],
        },
        safe=False,
        status=status.HTTP_410_GONE,
    )


def webhooks_getting_started(request):
    context = {"private": False}
    return render(request, "webhooks-getting-started.html", context)


def webhooks_docs(request, version=None):
    """Show the correct version of the webhooks docs"""

    context = {"private": False}
    try:
        return render(request, f"webhooks-docs-{version}.html", context)
    except TemplateDoesNotExist:
        return render(request, "webhooks-docs-vlatest.html", context)
