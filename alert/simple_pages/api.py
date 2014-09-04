import json
from django.conf import settings
from django.http import HttpResponse
from alert.lib import search_utils
from alert.lib.sunburnt import sunburnt


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


def coverage_data(request, court):
    """Provides coverage data for a court.

    Responds to either AJAX or regular requests.
    """
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    start_year = search_utils.get_court_start_year(conn, court)
    response = conn.raw_query(
        **search_utils.build_coverage_query(court, start_year)
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

    return HttpResponse(json.dumps(response), content_type='application/json')
