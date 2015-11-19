import logging
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.db.models import Sum
from django.utils.timezone import utc, make_aware
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render_to_response, get_object_or_404
from django.shortcuts import HttpResponseRedirect
from django.template import RequestContext
from django.views.decorators.cache import never_cache

from cl.alerts.forms import CreateAlertForm
from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import naturalduration
from cl.lib import search_utils
from cl.lib import sunburnt
from cl.lib.bot_detector import is_bot
from cl.search.forms import SearchForm, _clean_form
from cl import settings
from cl.search.models import Court, Opinion
from cl.stats import tally_stat, Stat
from cl.visualizations.models import SCOTUSMap

logger = logging.getLogger(__name__)


def do_search(request, rows=20, order_by=None, type=None):

    # Bind the search form.
    search_form = SearchForm(request.GET)
    if search_form.is_valid():
        cd = search_form.cleaned_data
        # Allows an override by calling methods.
        if order_by:
            cd['order_by'] = order_by
        if type:
            cd['type'] = type
        search_form = _clean_form(request, cd)

        try:
            if cd['type'] == 'o':
                conn = sunburnt.SolrInterface(
                    settings.SOLR_OPINION_URL, mode='r')
                stat_facet_fields = search_utils.place_facet_queries(cd, conn)
                status_facets = search_utils.make_stats_variable(
                    stat_facet_fields, search_form)
            elif cd['type'] == 'oa':
                conn = sunburnt.SolrInterface(
                    settings.SOLR_AUDIO_URL, mode='r')
                status_facets = None
            results_si = conn.raw_query(**search_utils.build_main_query(cd))

            courts = Court.objects.filter(in_use=True).values(
                'pk', 'short_name', 'jurisdiction',
                'has_oral_argument_scraper')
            courts, court_count_human, court_count = search_utils\
                .merge_form_with_courts(courts, search_form)

        except Exception, e:
            logger.warning("Error loading search with request: %s" % request.GET)
            logger.warning("Error was %s" % e)
            return {'error': True}

    else:
        # Invalid form, send it back
        logger.warning("Invalid form when loading search page with request: %s" % request.GET)
        return {'error': True}

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
     - In its most simple form, it is called via GET and without any
       parameters.
        --> This loads the homepage.
     - It might also be called with GET *with* parameters.
        --> This loads search results.
     - It might be called with a POST.
        --> This attempts to save an alert.

    It also has a few failure modes it needs to support:
     - It must react properly to an invalid alert form.
     - It must react properly to an invalid or failing search form.

    All of these paths have tests.
    """
    # Create a search string that does not contain the page numbers
    get_string = search_utils.make_get_string(request)
    get_string_sans_alert = search_utils.make_get_string(request, ['page', 'edit_alert'])
    render_dict = {
        'private': True,
        'get_string': get_string,
        'get_string_sans_alert': get_string_sans_alert,
    }

    if request.method == 'POST':
        # The user is trying to save an alert.
        alert_form = CreateAlertForm(request.POST, user=request.user)
        if alert_form.is_valid():
            cd = alert_form.cleaned_data

            # save the alert
            if request.POST.get('edit_alert'):
                # check if the user can edit this, or if they are url hacking
                alert = get_object_or_404(
                    Alert,
                    pk=request.POST.get('edit_alert'),
                    user=request.user,
                )
                alert_form = CreateAlertForm(cd, instance=alert,
                                             user=request.user)
                alert_form.save()
                action = "edited"
            else:
                alert_form = CreateAlertForm(cd, user=request.user)
                alert = alert_form.save(commit=False)
                alert.user = request.user
                alert.save()

                action = "created"
            messages.add_message(request, messages.SUCCESS,
                                 'Your alert was %s successfully.' % action)

            # and redirect to the alerts page
            return HttpResponseRedirect('/profile/alerts/')
        else:
            # Invalid form. Do the search again and show them the alert form
            # with the errors
            render_dict.update(do_search(request))
            render_dict.update({'alert_form': alert_form})
            return render_to_response(
                'search.html',
                render_dict,
                RequestContext(request),
            )

    else:
        # Either a search or the homepage
        if len(request.GET) == 0:
            # No parameters --> Homepage.
            if not is_bot(request):
                tally_stat('search.homepage_loaded')

            # Load the render_dict with good results that can be shown in the
            # "Latest Cases" section
            render_dict.update(do_search(request, rows=5,
                                         order_by='dateFiled desc'))
            # Get the results from the oral arguments as well
            oa_dict = do_search(request, rows=5, order_by='dateArgued desc',
                                type='oa')
            render_dict.update({'results_oa': oa_dict['results']})
            # But give it a fresh form for the advanced search section
            render_dict.update({'search_form': SearchForm(request.GET)})
            ten_days_ago = make_aware(datetime.today() - timedelta(days=10),
                                      utc)
            alerts_in_last_ten = Stat.objects.filter(
                    name__contains='alerts.sent',
                    date_logged__gte=ten_days_ago
                ).aggregate(Sum('count'))['count__sum']
            queries_in_last_ten = Stat.objects.filter(
                    name='search.results',
                    date_logged__gte=ten_days_ago
                ).aggregate(Sum('count'))['count__sum']
            bulk_in_last_ten = Stat.objects.filter(
                    name__contains='bulk_data',
                    date_logged__gte=ten_days_ago
                ).aggregate(Sum('count'))['count__sum']
            api_in_last_ten = Stat.objects.filter(
                    name__contains='api',
                    date_logged__gte=ten_days_ago
                ).aggregate(Sum('count'))['count__sum']
            users_in_last_ten = User.objects.filter(
                    date_joined__gte=ten_days_ago
                ).count()
            opinions_in_last_ten = Opinion.objects.filter(
                    date_created__gte=ten_days_ago
                ).count()
            oral_arguments_in_last_ten = Audio.objects.filter(
                    date_created__gte=ten_days_ago
                ).count()
            days_of_oa = naturalduration(
                    Audio.objects.aggregate(
                        Sum('duration')
                    )['duration__sum'],
                    as_dict=True,
                )['d']
            viz_in_last_ten = SCOTUSMap.objects.filter(
                    date_published__gte=ten_days_ago,
                    published=True,
                ).count()
            render_dict.update({
                'alerts_in_last_ten': alerts_in_last_ten,
                'queries_in_last_ten': queries_in_last_ten,
                'opinions_in_last_ten': opinions_in_last_ten,
                'oral_arguments_in_last_ten': oral_arguments_in_last_ten,
                'bulk_in_last_ten': bulk_in_last_ten,
                'api_in_last_ten': api_in_last_ten,
                'users_in_last_ten': users_in_last_ten,
                'days_of_oa': days_of_oa,
                'viz_in_last_ten': viz_in_last_ten,
                'private': False,  # VERY IMPORTANT!
            })
            return render_to_response(
                'homepage.html',
                render_dict,
                RequestContext(request)
            )
        else:
            # User placed a search or is trying to edit an alert
            if request.GET.get('edit_alert'):
                # They're editing an alert
                alert = get_object_or_404(
                    Alert,
                    pk=request.GET.get('edit_alert'),
                    user=request.user
                )
                alert_form = CreateAlertForm(
                    instance=alert,
                    initial={'query': get_string_sans_alert},
                    user=request.user,
                )
            else:
                # Just a regular search
                if not is_bot(request):
                    tally_stat('search.results')

                # Create bare-bones alert form.
                alert_form = CreateAlertForm(
                    initial={'query': get_string,
                             'rate': "dly"},
                    user=request.user
                )
            render_dict.update(do_search(request))
            render_dict.update({'alert_form': alert_form})
            return render_to_response(
                'search.html',
                render_dict,
                RequestContext(request),
            )
