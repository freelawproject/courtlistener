import logging
from datetime import datetime, timedelta
from django.contrib.auth.models import User
from django.db.models import Sum
from django.utils.timezone import utc, make_aware
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
from alert.search.models import Document
from alert.stats import tally_stat, Stat

logger = logging.getLogger(__name__)


def do_search(request, rows=20, order_by= None):
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    # Bind the search form.
    search_form = SearchForm(request.GET)
    if search_form.is_valid():
        cd = search_form.cleaned_data
        if order_by:
            cd['order_by'] = order_by
        search_form = _clean_form(request, cd)
        try:
            results_si = conn.raw_query(**search_utils.build_main_query(cd))
            stat_facet_fields = search_utils.place_facet_queries(cd, conn)
            status_facets = search_utils.make_stats_variable(stat_facet_fields, search_form)
            courts, court_count_human, court_count = search_utils.merge_form_with_courts(COURTS, search_form)
        except Exception, e:
            logger.warning("Error loading search page with request: %s" % request.GET)
            logger.warning("Error was %s" % e)
            return {'error': True}

    else:
        # Invalid form, send it back
        logger.warning("Invalid form when loading search page with request: %s" % request.GET)
        return  {'error': True}

    # Set up pagination
    try:
        paginator = Paginator(results_si, rows)
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
        return {'error': True}

    return {'search_form': search_form,
            'results': paged_results,
            'courts': courts,
            'court_count_human': court_count_human,
            'court_count': court_count,
            'status_facets': status_facets}


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
    render_dict = {
        'private': True,
        'get_string': get_string,
    }

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
            render_dict.update(do_search(request))
            render_dict.update({'alert_form': alert_form})
            return render_to_response(
                'search/search.html',
                render_dict,
                RequestContext(request),
            )

    else:
        # Either a search or the homepage
        if len(request.GET) == 0:
            # No parameters --> Homepage.
            if not is_bot(request):
                tally_stat('search.homepage_loaded')

            # Load the render_dict with good results that can be shown in the "Latest Cases" section
            render_dict.update(do_search(request, rows=5, order_by='dateFiled desc'))
            # But give it a fresh form for the advanced search section
            render_dict.update({'search_form': SearchForm(request.GET)})
            ten_days_ago = make_aware(datetime.today() - timedelta(days=10), utc)
            alerts_in_last_ten = Stat.objects\
                .filter(
                    name__contains='alerts.sent',
                    date_logged__gte=ten_days_ago)\
                .aggregate(Sum('count'))['count__sum']
            queries_in_last_ten = Stat.objects\
                .filter(
                    name='search.results',
                    date_logged__gte=ten_days_ago) \
                .aggregate(Sum('count'))['count__sum']
            bulk_in_last_ten = Stat.objects\
                .filter(
                    name__contains='bulk_data',
                    date_logged__gte=ten_days_ago)\
                .aggregate(Sum('count'))['count__sum']
            api_in_last_ten = Stat.objects \
                .filter(
                    name__contains='api',
                    date_logged__gte=ten_days_ago) \
                .aggregate(Sum('count'))['count__sum']
            users_in_last_ten = User.objects.filter(date_joined__gte=ten_days_ago).count()
            opinions_in_last_ten = Document.objects.filter(time_retrieved__gte=ten_days_ago).count()
            render_dict.update({
                'alerts_in_last_ten': alerts_in_last_ten,
                'queries_in_last_ten': queries_in_last_ten,
                'opinions_in_last_ten': opinions_in_last_ten,
                'bulk_in_last_ten': bulk_in_last_ten,
                'api_in_last_ten': api_in_last_ten,
                'users_in_last_ten': users_in_last_ten,
                'private': False
            })
            return render_to_response(
                'homepage.html',
                render_dict,
                RequestContext(request)
            )

        else:
            # User placed a search
            if not is_bot(request):
                tally_stat('search.results')
            # Create bare-bones alert form.
            alert_form = CreateAlertForm(initial={'alertText': get_string,
                                                  'alertFrequency': "dly"})
            render_dict.update(do_search(request))
            render_dict.update({'alert_form': alert_form})
            return render_to_response(
                'search/search.html',
                render_dict,
                RequestContext(request),
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
