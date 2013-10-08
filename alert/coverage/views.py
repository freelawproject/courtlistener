from alert.lib import search_utils
from alert.lib import sunburnt
from alert.search.models import Court

from django.conf import settings
from django.shortcuts import render_to_response
from django.template import RequestContext

import json


def calculate_grand_totals(data):
    """Iterates over the data and puts the totals together"""
    summed_court_data = {}
    for year_count_dict in data.values():
        for year, count in year_count_dict['years'].iteritems():
            try:
                summed_court_data[year] += count
            except KeyError:
                # New year field
                summed_court_data[year] = count

    return summed_court_data


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


def build_court_dicts(grand_total, courts):
    """Takes the court objects, and manipulates them into a list of more useful
    dictionaries"""
    court_dicts = [{'pk': 'all',
                    'short_name': u'All Courts'}]
    court_dicts.extend([{'pk': court.pk,
                         'short_name': court.short_name, }
                         #'notes': court.notes}
                       for court in courts])
    return court_dicts


def coverage_graph(request):
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    courts = Court.objects.filter(in_use=True)
    data = {}
    grand_total = 0
    non_empty_courts = []  # To make sure a court with no items doesn't appear in the list
    for court in courts:
        start_year = search_utils.get_court_start_year(conn, court)
        years = {}
        total_docs = 0
        response = conn.raw_query(
            **search_utils.build_coverage_query(court, start_year)).execute()
        counts = response.facet_counts.facet_ranges[0][1][0][1]
        counts = strip_trailing_zeroes(counts)
        for date_string, count in counts:
            years[date_string[:7]] = count
            total_docs += count
        if total_docs > 0:
            non_empty_courts.append(court)
            data[court.pk] = {'years': years,
                              'total_docs': total_docs}
            grand_total += total_docs
    data[u'all'] = {'years': calculate_grand_totals(data),
                    'total_docs': grand_total}
    coverage_data = json.dumps(data)

    court_dicts = build_court_dicts(grand_total, non_empty_courts)
    courts_json = json.dumps(court_dicts)
    return render_to_response(
        'coverage/coverage_graph.html',
        {'sorted_courts': courts_json,
         'coverage_data': coverage_data,
         'private': False},
        RequestContext(request))
