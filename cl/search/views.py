import logging
import re
import traceback
from datetime import date, datetime, timedelta
from urllib import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.urls import reverse
from django.db.models import Sum, Count
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.utils.timezone import utc, make_aware
from django.views.decorators.cache import never_cache
from requests import RequestException
from scorched.exc import SolrError

from cl.alerts.forms import CreateAlertForm
from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import naturalduration
from cl.lib.bot_detector import is_bot
from cl.lib.ratelimiter import ratelimit_if_not_whitelisted
from cl.lib.redis_utils import make_redis_interface
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.search_utils import build_main_query, get_query_citation, \
    make_stats_variable, merge_form_with_courts, make_get_string, \
    regroup_snippets, get_mlt_query
from cl.search.forms import SearchForm, _clean_form
from cl.search.models import Court, Opinion
from cl.stats.models import Stat
from cl.stats.utils import tally_stat
from cl.visualizations.models import SCOTUSMap

logger = logging.getLogger(__name__)


def check_pagination_depth(page_number):
    """Check if the pagination is too deep (indicating a crawler)"""
    max_search_pagination_depth = 100
    if page_number > max_search_pagination_depth:
        logger.warning("Query depth of %s denied access (probably a "
                       "crawler)", page_number)
        raise PermissionDenied


def get_solr_result_objects(cd, facet):
    """Note that this doesn't run the query yet. Not until the
    pagination is run.
    """
    search_type = cd['type']
    if search_type == 'o':
        # This is a `related:<pk>` prefix query?
        related_prefix_match = re.search(r'(^|\s)(?P<pfx>related:(?P<pk>[0-9]+))($|\s)', cd['q'])
        if related_prefix_match:
            results = get_mlt_query(
                cd,
                facet,
                settings.SOLR_OPINION_URL,
                settings.SOLR_OPINION_HL_FIELDS,
                related_prefix_match.group('pk'),
                cd['q'].replace(related_prefix_match.group('pfx'), '')
            )
        else:
            # Default search interface
            si = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode='r')
            results = si.query().add_extra(**build_main_query(cd, facet=facet))

    elif search_type == 'r':
        si = ExtraSolrInterface(settings.SOLR_RECAP_URL, mode='r')
        results = si.query().add_extra(**build_main_query(cd, facet=facet))
    elif search_type == 'oa':
        si = ExtraSolrInterface(settings.SOLR_AUDIO_URL, mode='r')
        results = si.query().add_extra(**build_main_query(cd, facet=facet))
    elif search_type == 'p':
        si = ExtraSolrInterface(settings.SOLR_PEOPLE_URL, mode='r')
        results = si.query().add_extra(**build_main_query(cd, facet=facet))
    else:
        raise NotImplementedError("Unknown search type: %s" % search_type)

    return results


def paginate_cached_solr_results(request, cd, results, rows, cache_key):
    # Run the query and set up pagination
    if cache_key is not None:
        paged_results = cache.get(cache_key)
        if paged_results is not None:
            return paged_results

    page = int(request.GET.get('page', 1))
    check_pagination_depth(page)

    if cd['type'] == 'r':
        rows = 10

    paginator = Paginator(results, rows)
    try:
        paged_results = paginator.page(page)
    except PageNotAnInteger:
        paged_results = paginator.page(1)
    except EmptyPage:
        # Page is out of range (e.g. 9999), deliver last page.
        paged_results = paginator.page(paginator.num_pages)

    # Post processing of the results
    regroup_snippets(paged_results)

    if cache_key is not None:
        six_hours = 60 * 60 * 6
        cache.set(cache_key, paged_results, six_hours)

    return paged_results


def do_search(request, rows=20, order_by=None, type=None, facet=True,
              cache_key=None):
    """Do all the difficult solr work.

    :param request: The request made by the user
    :param rows: The number of solr results to request
    :param order_by: An opportunity to override the ordering of the search
    results
    :param type: An opportunity to override the type
    :param facet: Whether to complete faceting in the query
    :param cache_key: A cache key with which to save the results. Note that it
    does not do anything clever with the actual query, so if you use this, your
    cache key should *already* have factored in the query. If None, no caching
    is set or used. Results are saved for six hours.
    :return A big dict of variables for use in the search results, homepage, or
    other location.
    """
    query_citation = None
    error = False
    paged_results = None
    search_form = SearchForm(request.GET)
    courts = Court.objects.filter(in_use=True)

    if search_form.is_valid():
        cd = search_form.cleaned_data
        # Allows an override by calling methods.
        if order_by is not None:
            cd['order_by'] = order_by
        if type is not None:
            cd['type'] = type

        # Do the query, hitting the cache if desired
        # noinspection PyBroadException
        try:
            results = get_solr_result_objects(cd, facet)
            paged_results = paginate_cached_solr_results(request, cd, results,
                                                         rows, cache_key)
        except (NotImplementedError, RequestException, SolrError) as e:
            error = True
            logger.warning("Error loading search page with "
                           "request: %s" % request.GET)
            logger.warning("Error was: %s" % e)
            if settings.DEBUG is True:
                traceback.print_exc()

        # A couple special variables for particular search types
        search_form = _clean_form(request, cd, courts)
        if cd['type'] == 'o':
            query_citation = get_query_citation(cd)
        elif cd['type'] == 'r':
            panels = Court.FEDERAL_BANKRUPTCY_PANEL
            courts = (courts.filter(pacer_court_id__isnull=False,
                                    end_date__isnull=True)
                            .exclude(jurisdiction=panels))
    else:
        error = True

    courts, court_count_human, court_count = merge_form_with_courts(
        courts, search_form)
    search_summary_str = search_form.as_text(court_count, court_count_human)

    return {
        'results': paged_results,
        'facet_fields': make_stats_variable(search_form, paged_results),
        'search_form': search_form,
        'search_summary_str': search_summary_str,
        'courts': courts,
        'court_count_human': court_count_human,
        'court_count': court_count,
        'query_citation': query_citation,
        'error': error,
    }


def get_homepage_stats():
    """Get any stats that are displayed on the homepage and return them as a
    dict
    """
    r = make_redis_interface('STATS')
    ten_days_ago = make_aware(datetime.today() - timedelta(days=10), utc)
    last_ten_days = ['api:v3.d:%s.count' %
                     (date.today() - timedelta(days=x)).isoformat()
                     for x in range(0, 10)]
    homepage_data = {
        'alerts_in_last_ten': Stat.objects.filter(
            name__contains='alerts.sent',
            date_logged__gte=ten_days_ago
        ).aggregate(Sum('count'))['count__sum'],
        'queries_in_last_ten': Stat.objects.filter(
            name='search.results',
            date_logged__gte=ten_days_ago
        ).aggregate(Sum('count'))['count__sum'],
        'bulk_in_last_ten': Stat.objects.filter(
            name__contains='bulk_data',
            date_logged__gte=ten_days_ago
        ).aggregate(Sum('count'))['count__sum'],
        'opinions_in_last_ten': Opinion.objects.filter(
            date_created__gte=ten_days_ago
        ).count(),
        'oral_arguments_in_last_ten': Audio.objects.filter(
            date_created__gte=ten_days_ago
        ).count(),
        'api_in_last_ten': sum(
            [int(result) for result in
             r.mget(*last_ten_days) if result is not None]
        ),
        'users_in_last_ten': User.objects.filter(
            date_joined__gte=ten_days_ago
        ).count(),
        'days_of_oa': naturalduration(
            Audio.objects.aggregate(
                Sum('duration')
            )['duration__sum'],
            as_dict=True,
        )['d'],
        'viz_in_last_ten': SCOTUSMap.objects.filter(
            date_published__gte=ten_days_ago,
            published=True,
        ).count(),
        'visualizations': SCOTUSMap.objects.filter(
            published=True,
            deleted=False,
        ).annotate(
            Count('clusters'),
        ).filter(
            # Ensures that we only show good stuff on homepage
            clusters__count__gt=10,
        ).order_by(
            '-date_published',
            '-date_modified',
            '-date_created',
        )[:1],
        'private': False,  # VERY IMPORTANT!
    }
    return homepage_data


@never_cache
@ratelimit_if_not_whitelisted
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
    get_string = make_get_string(request)
    get_string_sans_alert = make_get_string(request, ['page', 'edit_alert'])
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
            return HttpResponseRedirect(reverse("profile_alerts"))
        else:
            # Invalid form. Do the search again and show them the alert form
            # with the errors
            render_dict.update(do_search(request))
            render_dict.update({'alert_form': alert_form})
            return render(request, 'search.html', render_dict)

    else:
        # Either a search or the homepage
        if len(request.GET) == 0:
            # No parameters --> Homepage.
            if not is_bot(request):
                tally_stat('search.homepage_loaded')

            # Ensure we get nothing from the future.
            request.GET = request.GET.copy()  # Makes it mutable
            request.GET['filed_before'] = date.today()

            # Load the render_dict with good results that can be shown in the
            # "Latest Cases" section
            render_dict.update(do_search(
                request, rows=5, order_by='dateFiled desc', facet=False,
                cache_key='homepage-data-o'))
            # Get the results from the oral arguments as well
            render_dict.update({'results_oa': do_search(
                request, rows=5, order_by='dateArgued desc', type='oa',
                facet=False, cache_key='homepage-data-oa')['results']})

            # But give it a fresh form for the advanced search section
            render_dict.update({'search_form': SearchForm(request.GET)})

            # Get a bunch of stats.
            stats = get_homepage_stats()
            render_dict.update(stats)

            return render(request, 'homepage.html', render_dict)
        else:
            # User placed a search or is trying to edit an alert
            if request.GET.get('edit_alert'):
                # They're editing an alert
                if request.user.is_anonymous:
                    return HttpResponseRedirect(
                        "{path}?next={next}{encoded_params}".format(
                            path=reverse('sign-in'),
                            next=request.path,
                            encoded_params=quote("?" + request.GET.urlencode())
                        ))
                else:
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
            # Set the value to the query as a convenience
            alert_form.fields['name'].widget.attrs['value'] = \
                render_dict['search_summary_str']
            render_dict.update({'alert_form': alert_form})
            return render(request, 'search.html', render_dict)


def advanced(request):
    render_dict = {'private': False}

    # I'm not thrilled about how this is repeating URLs in a view.
    if request.path == reverse('advanced_o'):
        obj_type = 'o'
        # Needed b/c of facet values.

        o_results = do_search(request, rows=1, type=obj_type, facet=True,
                              cache_key='opinion-homepage-results')
        render_dict.update(o_results)
        render_dict['search_form'] = SearchForm({'type': obj_type})
        return render(request, 'advanced.html', render_dict)
    else:
        courts = Court.objects.filter(in_use=True)
        if request.path == reverse('advanced_r'):
            obj_type = 'r'
            courts = courts.filter(
                pacer_court_id__isnull=False,
                end_date__isnull=True,
            ).exclude(
                jurisdiction=Court.FEDERAL_BANKRUPTCY_PANEL,
            )
        elif request.path == reverse('advanced_oa'):
            obj_type = 'oa'
        elif request.path == reverse('advanced_p'):
            obj_type = 'p'
        else:
            raise NotImplementedError("Unknown path: %s" % request.path)

        search_form = SearchForm({'type': obj_type})
        courts, court_count_human, court_count = merge_form_with_courts(
            courts, search_form)
        render_dict.update({
            'search_form': search_form,
            'courts': courts,
            'court_count_human': court_count_human,
            'court_count': court_count,
        })
        return render(request, 'advanced.html', render_dict)
