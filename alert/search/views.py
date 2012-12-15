# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from alert.alerts.forms import CreateAlertForm
from alert.lib import search_utils
from alert.lib import sunburnt
from alert.search.forms import SearchForm

from django.conf import settings
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render_to_response
from django.http import HttpResponseNotFound
from django.shortcuts import HttpResponseRedirect
from django.template import loader, RequestContext
from django.views.decorators.cache import never_cache

from datetime import date
import json


@never_cache
def show_results(request):
    '''Show the results for a query

    Implements a parallel faceted search interface with Solr as the backend.
    '''

    # Create a search string that does not contain the page numbers
    get_string = search_utils.make_get_string(request)

    # this handles the alert creation form.
    if request.method == 'POST':
        # an alert has been created
        alert_form = CreateAlertForm(request.POST)
        if alert_form.is_valid():
            cd = alert_form.cleaned_data

            # save the alert
            a = CreateAlertForm(cd)
            alert = a.save()

            # associate the user with the alert
            up = request.user.get_profile()
            up.alert.add(alert)
            messages.add_message(request, messages.SUCCESS,
                                 'Your alert was created successfully.')

            # and redirect to the alerts page
            return HttpResponseRedirect('/profile/alerts/')
    else:
        # the form is loading for the first time, load it, then load the rest
        # of the page
        alert_form = CreateAlertForm(initial={'alertText': get_string,
                                              'alertFrequency': "dly"})

    '''
    Code beyond this point will be run if the alert form failed, or if the
    submission was a GET request. Beyond this point, we run the searches.
    '''

    try:
        # Bind the search form if a search has been placed
        request.GET['q']
        search_form = SearchForm(request.GET)
    except KeyError:
        # No search placed. Show default form.
        search_form = SearchForm()
    # Run the query
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    if search_form.is_bound:
        if search_form.is_valid():
            cd = search_form.cleaned_data
            try:
                results_si = conn.raw_query(**search_utils.build_main_query(cd))
                court_facet_fields, stat_facet_fields, count = search_utils.place_facet_queries(cd)
                # Create facet variables that can be used in our templates
                court_facets = search_utils.make_facets_variable(
                                 court_facet_fields, search_form, 'court_exact', 'court_')
                status_facets = search_utils.make_facets_variable(
                                 stat_facet_fields, search_form, 'status_exact', 'stat_')
            except:
                return render_to_response('search/search.html',
                                          {'error': True},
                                          RequestContext(request))

            # Make a copy of request.GET so it is mutable, and we make
            # some adjustments that we want to see in the rendered form.
            mutable_get = request.GET.copy()
            if search_form.is_valid():
                # Send the user the cleaned up query
                cd = search_form.cleaned_data
                mutable_get['q'] = cd['q']
                if mutable_get.get('filed_before') and cd.get('filed_before') is not None:
                    mutable_get['filed_before'] = date.strftime(cd['filed_before'], '%Y-%m-%d')
                if mutable_get.get('filed_after') and cd.get('filed_before') is not None:
                    mutable_get['filed_after'] = date.strftime(cd['filed_after'], '%Y-%m-%d') or None
                mutable_get['court_all'] = cd['court_all']
            # Always reset the radio box to refine
            mutable_get['refine'] = 'refine'
            search_form = SearchForm(mutable_get)
        else:
            # Invalid form, send it back
            return render_to_response(
                          'search/search.html',
                          {'error': True},
                          RequestContext(request))

    else:
        # Unbound form, first time the user has seen the page.
        try:
            # Gather the initial values
            initial_values = {}
            for k, v in dict(search_form.fields).iteritems():
                initial_values[k] = v.initial
            results_si = conn.raw_query(**search_utils.build_main_query(initial_values))
            court_facet_fields, stat_facet_fields, count = search_utils.place_facet_queries(initial_values)
            # Create facet variables that can be used in our templates
            court_facets = search_utils.make_facets_variable(
                             court_facet_fields, search_form, 'court_exact', 'court_')
            status_facets = search_utils.make_facets_variable(
                             stat_facet_fields, search_form, 'status_exact', 'stat_')
        except:
            return render_to_response('search/search.html',
                                          {'error': True},
                                          RequestContext(request))

    # Set up pagination
    try:
        paginator = Paginator(results_si, 20)
        page = request.GET.get('page', 1)
        try:
            paged_results = paginator.page(page)
        except PageNotAnInteger:
            # If page is not an integer, deliver first page.
            paged_results = paginator.page(1)
        except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of results.
            paged_results = paginator.page(paginator.num_pages)
    except:
        # Catches any Solr errors, and simply aborts.
        return render_to_response('search/search.html',
                                      {'error': True},
                                      RequestContext(request))
    return render_to_response(
                  'search/search.html',
                  {'search_form': search_form, 'alert_form': alert_form,
                   'results': paged_results, 'court_facets': court_facets,
                   'status_facets': status_facets, 'get_string': get_string,
                   'count': count},
                  RequestContext(request))


def catch_404_and_search(request):
    '''If somebody goes to a page that would normally return a 404, it's better
    to instead redirect them to a search for that term. This increases their
    odds of finding what they're looking for and also provides a handy
    shortcut for advanced users.'''
    messages.add_message(request,
                         messages.ERROR,
                         "There's no valid page at this location. Perhaps "
                         "these search results will help you find what "
                         "you're looking for&hellip;")
    full_path = request.get_full_path().strip('/')
    if '/' in full_path:
        # Send to proper 404 page.
        t = loader.get_template('404.html')
        return HttpResponseNotFound(t.render(RequestContext(request, {'request_path': request.path})))
    else:
        # Place query for the URL
        mutable_get = request.GET.copy()
        mutable_get['q'] = full_path
        request.GET = mutable_get
        return HttpResponseNotFound(show_results(request))


def tools_page(request):
    return render_to_response('tools.html', {}, RequestContext(request))


def browser_warning(request):
    return render_to_response('browser_warning.html', {}, RequestContext(request))
