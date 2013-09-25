import logging
from alert.alerts.forms import CreateAlertForm
from alert.lib import search_utils
from alert.lib import sunburnt
from alert.lib.bot_detector import is_bot
from alert.search.forms import SearchForm

from alert import settings
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render_to_response
from django.shortcuts import HttpResponseRedirect
from django.template import RequestContext
from django.views.decorators.cache import never_cache
from alert.stats import tally_stat

logger = logging.getLogger(__name__)


def _clean_form(request, cd):
    """Returns cleaned up values as a Form object.
    """
    # Make a copy of request.GET so it is mutable
    mutable_get = request.GET.copy()

    # Send the user the cleaned up query
    mutable_get['q'] = cd['q']
    if mutable_get.get('filed_before') and cd.get('filed_before') is not None:
        # Don't use strftime since it won't work prior to 1900.
        before = cd['filed_before']
        mutable_get['filed_before'] = '%s-%02d-%02d' % \
                                      (before.year, before.month, before.day)
    if mutable_get.get('filed_after') and cd.get('filed_before') is not None:
        after = cd['filed_after']
        mutable_get['filed_after'] = '%s-%02d-%02d' % \
                                     (after.year, after.month, after.day)
    mutable_get['court_all'] = cd['court_all']

    return SearchForm(mutable_get)


@never_cache
def show_results(request):
    """Show the results for a query

    Implements a parallel faceted search interface with Solr as the backend.
    """
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
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    if len(request.GET) > 0:
        # Bind the search form.
        search_form = SearchForm(request.GET)
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
                if not is_bot(request):
                    tally_stat('search.results')
            except Exception, e:
                logger.warning("Error loading search page with request: %s" % request.GET)
                return render_to_response(
                    'search/search.html',
                    {'error': True, 'private': True},
                    RequestContext(request)
                )

            search_form = _clean_form(request, cd)

        else:
            # Invalid form, send it back
            logger.warning("Invalid form when loading search page with request: %s" % request.GET)
            return render_to_response(
                'search/search.html',
                {'error': True, 'private': True},
                RequestContext(request)
            )

    else:
        # No search placed. Show default page after placing the needed queries.
        search_form = SearchForm()

        # Gather the initial values
        initial_values = {}
        for k, v in dict(search_form.fields).iteritems():
            initial_values[k] = v.initial
        # Make the queries
        results_si = conn.raw_query(**search_utils.build_main_query(initial_values))
        court_facet_fields, stat_facet_fields, count = search_utils.place_facet_queries(initial_values)
        court_facets = search_utils.make_facets_variable(
            court_facet_fields, search_form, 'court_exact', 'court_')
        status_facets = search_utils.make_facets_variable(
            stat_facet_fields, search_form, 'status_exact', 'stat_')

    # Set up pagination
    try:
        paginator = Paginator(results_si, 20)
        page = request.GET.get('page', 1)
        private = True
        if page == 1:
            # It's the homepage -- not private.
            private = False
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
        logger.warning("Error loading pagination on search page with request: %s" % request.GET)
        return render_to_response('search/search.html',
                                  {'error': True, 'private': True},
                                  RequestContext(request))
    return render_to_response(
        'search/search.html',
        {'search_form': search_form,
         'alert_form': alert_form,
         'results': paged_results,
         'court_facets': court_facets,
         'status_facets': status_facets,
         'get_string': get_string,
         'count': count,
         'private': private},
        RequestContext(request)
    )


def tools_page(request):
    return render_to_response('tools.html',
                              {'private': False},
                              RequestContext(request))


def browser_warning(request):
    return render_to_response('browser_warning.html',
                              {'private': False},
                              RequestContext(request))
