from django.shortcuts import render_to_response
from django.template import RequestContext
from alert.lib import search_utils
from alert.lib.sunburnt import sunburnt
from alert.search.models import Court
from alert import settings


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


def court_index(request):
    """Shows the information we have available for the courts."""
    courts = Court.objects.exclude(jurisdiction='T')  # Non-testing courts
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    response = conn.raw_query(
        **search_utils.build_court_count_query()).execute()
    court_count_tuples = response.facet_counts.facet_fields['court_exact']
    courts = annotate_courts_with_counts(courts, court_count_tuples)
    return render_to_response('api/jurisdictions.html',
                              {'courts': courts,
                               'private': False},
                              RequestContext(request))
