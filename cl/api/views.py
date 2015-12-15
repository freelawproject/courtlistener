import json
import os

from cl import settings
from cl.lib import magic, search_utils, sunburnt
from cl.search.models import Court
from cl.stats import tally_stat

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from rest_framework import status


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
    courts = Court.objects.exclude(jurisdiction='T')  # Non-testing courts
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    response = conn.raw_query(
        **search_utils.build_court_count_query()).execute()
    court_count_tuples = response.facet_counts.facet_fields['court_exact']
    courts = annotate_courts_with_counts(courts, court_count_tuples)
    return courts


def court_index(request):
    """Shows the information we have available for the courts."""
    courts = make_court_variable()
    return render_to_response(
        'jurisdictions.html',
        {'courts': courts,
         'private': False},
        RequestContext(request)
    )


def rest_docs(request, version):
    """Show the correct version of the rest docs"""
    courts = make_court_variable()
    court_count = len(courts)
    if version is None:
        version = 'vlatest'
    return render_to_response(
        'rest-docs-%s.html' % version,
        {'court_count': court_count,
         'courts': courts,
         'private': False},
        RequestContext(request)
    )


def api_index(request):
    court_count = Court.objects.exclude(
        jurisdiction='T'
    ).count()  # Non-testing courts
    return render_to_response(
        'docs.html',
        {'court_count': court_count,
         'private': False},
        RequestContext(request)
    )


def bulk_data_index(request):
    """Shows an index page for the dumps."""
    courts = make_court_variable()
    court_count = len(courts)
    return render_to_response(
        'bulk-data.html',
        {'court_count': court_count,
         'courts': courts,
         'private': False},
        RequestContext(request)
    )


def serve_pagerank_file(request):
    """Serves the bulk pagerank file from the bulk data directory."""
    file_loc = settings.BULK_DATA_DIR + "external_pagerank"
    file_name = file_loc.split('/')[-1]
    try:
        mimetype = magic.from_file(file_loc, mime=True)
    except IOError:
        raise Http404('Unable to locate external_pagerank file in %s' % settings.BULK_DATA_DIR)
    response = HttpResponse()
    response['X-Sendfile'] = os.path.join(file_loc)
    response['Content-Disposition'] = 'attachment; filename="%s"' % file_name.encode('utf-8')
    response['Content-Type'] = mimetype
    tally_stat('bulk_data.pagerank.served')
    return response


def strip_trailing_zeroes(data):
    """Removes zeroes from the end of the court data

    Some courts only have values through to a certain date, but we don't
    check for that in our queries. Instead, we truncate any zero-values that
    occur at the end of their stats.
    """
    i = len(data) - 1
    while i > 0:
        if data[i][1] == 0:
            i -= 1
        else:
            break

    return data[:i + 1]


def coverage_data(request, version, court):
    """Provides coverage data for a court.

    Responds to either AJAX or regular requests.
    """

    if court != 'all':
        court_str = get_object_or_404(Court, pk=court).pk
    else:
        court_str = 'all'
    q = request.GET.get('q')
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    start_year = search_utils.get_court_start_year(conn, court_str)
    response = conn.raw_query(
        **search_utils.build_coverage_query(court_str, start_year, q)
    ).execute()
    counts = response.facet_counts.facet_ranges[0][1][0][1]
    counts = strip_trailing_zeroes(counts)

    # Calculate the totals
    annual_counts = {}
    total_docs = 0
    for date_string, count in counts:
        annual_counts[date_string[:4]] = count
        total_docs += count
    response = {
        'annual_counts': annual_counts,
        'total': total_docs,
    }

    return JsonResponse(json.dumps(response), safe=False)


def deprecated_api(request, v):
    return JsonResponse(
        {
            "meta": {
                "status": "This endpoint is deprecated. Please upgrade to the "
                          "newest version of the API.",
            },
            "objects": []
        },
        safe=False,
        status=status.HTTP_410_GONE
    )
