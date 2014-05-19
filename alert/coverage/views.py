from django.db.models import Count
from alert.search.models import Court, Document

from django.shortcuts import render_to_response
from django.template import RequestContext

import json


def build_court_dicts(courts):
    """Takes the court objects, and manipulates them into a list of more useful
    dictionaries"""
    court_dicts = [{'pk': 'all',
                    'short_name': u'All Courts'}]
    court_dicts.extend([{'pk': court.pk,
                         'short_name': court.full_name, }
                         #'notes': court.notes}
                        for court in courts])
    return court_dicts


def coverage_graph(request):
    courts = Court.objects.filter(in_use=True)
    courts_json = json.dumps(build_court_dicts(courts))

    # Build up the sourcing stats.
    counts = Document.objects.values('source').annotate(Count('source'))
    count_pro = 0
    count_lawbox = 0
    count_scraper = 0
    for d in counts:
        if 'R' in d['source']:
            count_pro += d['source__count']
        if 'C' in d['source']:
            count_scraper += d['source__count']
        if 'L' in d['source']:
            count_lawbox += d['source__count']

    courts_with_scrapers = Court.objects.filter(in_use=True, has_scraper=True)
    return render_to_response('coverage/coverage_graph.html',
                              {'sorted_courts': courts_json,
                               'count_pro': count_pro,
                               'count_lawbox': count_lawbox,
                               'count_scraper': count_scraper,
                               'courts_with_scrapers': courts_with_scrapers,
                               'private': False},
                              RequestContext(request))
