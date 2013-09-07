from django.shortcuts import render_to_response
from django.template import RequestContext
from alert.search.models import Court


def court_index(request):
    """Shows the information we have available for the courts."""
    courts = Court.objects.exclude(jurisdiction='T')  # Non-testing courts
    return render_to_response('api/jurisdictions.html',
                              {'courts': courts,
                               'private': False},
                              RequestContext(request))
