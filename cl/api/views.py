import os

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from rest_framework import status

from cl.lib import magic, sunburnt
from cl.lib.search_utils import build_coverage_query, build_court_count_query
from cl.search.models import Court
from cl.stats.utils import tally_stat


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
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    response = conn.raw_query(**build_court_count_query()).execute()
    court_count_tuples = response.facet_counts.facet_fields['court_exact']
    courts = annotate_courts_with_counts(courts, court_count_tuples)
    return courts


def court_index(request):
    """Shows the information we have available for the courts."""
    courts = make_court_variable()
    return render(request, 'jurisdictions.html', {
        'courts': courts,
        'private': False
    })


def rest_docs(request, version):
    """Show the correct version of the rest docs"""
    courts = make_court_variable()
    court_count = len(courts)
    if version is None:
        version = 'vlatest'
    return render(request, 'rest-docs-%s.html' % version, {
        'court_count': court_count,
        'courts': courts,
        'private': False
    })


def api_index(request):
    court_count = Court.objects.exclude(
        jurisdiction=Court.TESTING_COURT
    ).count()
    return render(request, 'docs.html', {
        'court_count': court_count,
        'private': False
    })


def replication_docs(request):
    return render(request, 'replication.html', {
        'private': False,
    })


def bulk_data_index(request):
    """Shows an index page for the dumps."""
    courts = make_court_variable()
    court_count = len(courts)
    return render(request, 'bulk-data.html', {
        'court_count': court_count,
        'courts': courts,
        'private': False
    })


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

    return data[start:end+1]


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
    response = conn.raw_query(**build_coverage_query(court_str, q)).execute()
    counts = response.facet_counts.facet_ranges[0][1][0][1]
    counts = strip_zero_years(counts)

    # Calculate the totals
    annual_counts = {}
    total_docs = 0
    for date_string, count in counts:
        annual_counts[date_string[:4]] = count
        total_docs += count

    return JsonResponse({
        'annual_counts': annual_counts,
        'total': total_docs,
    }, safe=True)


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
