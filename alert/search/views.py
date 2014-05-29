import logging
from alert.alerts.forms import CreateAlertForm
from alert.lib import search_utils
from alert.lib import sunburnt
from alert.lib.bot_detector import is_bot
from alert.search.forms import SearchForm, COURTS, _clean_form

from alert import settings
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render_to_response
from django.shortcuts import HttpResponseRedirect
from django.template import RequestContext
from django.views.decorators.cache import never_cache
from alert.stats import tally_stat

logger = logging.getLogger(__name__)


def do_search(request, get_string, alert_form=None, template='search/search.html', privacy=True):
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    # Bind the search form.
    search_form = SearchForm(request.GET)
    if search_form.is_valid():
        cd = search_form.cleaned_data
        search_form = _clean_form(request, cd)
        try:
            results_si = conn.raw_query(**search_utils.build_main_query(cd))
            stat_facet_fields = search_utils.place_facet_queries(cd, conn)
            status_facets = search_utils.make_stats_variable(stat_facet_fields, search_form)
            courts, court_count = search_utils.merge_form_with_courts(COURTS, search_form)
        except Exception, e:
            logger.warning("Error loading search page with request: %s" % request.GET)
            logger.warning("Error was %s" % e)
            return render_to_response(
                template,
                {'error': True, 'private': privacy},
                RequestContext(request)
            )

    else:
        # Invalid form, send it back
        logger.warning("Invalid form when loading search page with request: %s" % request.GET)
        return render_to_response(
            template,
            {'error': True, 'private': privacy},
            RequestContext(request)
        )

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
    except Exception, e:
        # Catches any Solr errors, and aborts.
        logger.warning("Error loading pagination on search page with request: %s" % request.GET)
        logger.warning("Error was: %s" % e)
        return render_to_response(
            template,
            {'error': True, 'private': privacy},
            RequestContext(request)
        )

    return render_to_response(
        template,
        {'search_form': search_form,
         'alert_form': alert_form,
         'results': paged_results,
         'courts': courts,
         'court_count': court_count,
         'status_facets': status_facets,
         'get_string': get_string,
         'private': privacy},
        RequestContext(request)
    )

@never_cache
def show_results(request):
    """
    This view can vary significantly, depending on how it is called:
     - In its most simple form, it is called via GET and without any parameters.
        --> This loads the homepage.
     - It might also be called with GET *with* parameters.
        --> This loads search results.
     - It might be called with a POST.
        --> This attempts to save an alert.

    It also has a few failure modes it needs to support:
     - It must react properly to an invalid alert form.
     - It must react properly to an invalid or failing search form.

    All of these paths have tests in tests.py.
    """
    # Create a search string that does not contain the page numbers
    get_string = search_utils.make_get_string(request)

    if request.method == 'POST':
        # The user is trying to save an alert.
        alert_form = CreateAlertForm(request.POST)
        if alert_form.is_valid():
            cd = alert_form.cleaned_data

            # save the alert
            a = CreateAlertForm(cd)
            alert = a.save()

            # associate the user with the alert
            up = request.user.profile
            up.alert.add(alert)
            messages.add_message(request, messages.SUCCESS,
                                 'Your alert was created successfully.')

            # and redirect to the alerts page
            return HttpResponseRedirect('/profile/alerts/')
        else:
            # Invalid form. Do the search again and show them the alert form with the errors
            return do_search(
                request,
                get_string,
                alert_form=alert_form,
            )

    else:
        # Either a search or the homepage
        if len(request.GET) == 0:
            # No parameters --> Homepage.
            if not is_bot(request):
                tally_stat('search.homepage_loaded')
            return do_search(
                request,
                get_string,
                template='homepage.html',
                privacy=False,
            )

        else:
            # User placed a search
            if not is_bot(request):
                tally_stat('search.results')
            # Create bare-bones alert form.
            alert_form = CreateAlertForm(initial={'alertText': get_string,
                                                  'alertFrequency': "dly"})
            return do_search(
                request,
                get_string,
                alert_form=alert_form
            )


def tools_page(request):
    return render_to_response(
        'tools.html',
        {'private': False},
        RequestContext(request)
    )


def browser_warning(request):
    return render_to_response(
        'browser_warning.html',
        {'private': True},
        RequestContext(request)
    )
