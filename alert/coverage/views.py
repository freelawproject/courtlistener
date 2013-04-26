from alert.lib import search_utils
from alert.lib import sunburnt
from alert.search.models import Court

from django.conf import settings
from django.shortcuts import render_to_response
from django.template import RequestContext

import json


def calculate_grand_totals(data):
    '''Iterates over the data and puts the totals together'''
    summed_court_data = {}
    for year_count_dict in data.values():
        for year, count in year_count_dict.iteritems():
            try:
                summed_court_data[year] += count
            except KeyError:
                # New year field
                summed_court_data[year] = count

    return summed_court_data


def coverage_graph(request):
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    courts = Court.objects.filter(in_use=True)
    data = {}
    grand_total = 0
    for court in courts:
        start_year = search_utils.get_court_start_year(conn, court)
        years = {}
        total_docs = 0
        response = conn.raw_query(
            **search_utils.build_coverage_query(court, start_year)).execute()
        dateFiled, value = response.facet_counts.facet_ranges[0]
        name, counts = value[0]
        for date_string, count in counts:
            years[date_string[:7]] = count
            total_docs += count
        data[court.short_name] = years
        court.total_docs = total_docs
        grand_total += total_docs
    data[u'All Courts'] = calculate_grand_totals(data)
    coverage_data = json.dumps(data)
    court_dicts = [{'total_docs': grand_total, 'short_name': u'All Courts'}]
    court_dicts.extend([{'short_name': court.short_name,
                    'total_docs': court.total_docs}
                    #'notes': court.notes}
                   for court in courts])
    courts_json = json.dumps(court_dicts)
    return render_to_response(
        'coverage/coverage_graph.html',
        {'courts': courts_json,
         'coverage_data': coverage_data,
         'private': False},
        RequestContext(request))
