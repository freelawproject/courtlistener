from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.decorators.cache import never_cache


@login_required
@never_cache
def view_donations(request):
    return render_to_response('profile/donations.html',
                              {'private': False},
                              RequestContext(request))
