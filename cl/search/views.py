import logging
import re
import traceback
from datetime import date, datetime, timedelta
from urllib import quote

import redis
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.core.urlresolvers import reverse
from django.db.models import Sum, Count
from django.shortcuts import HttpResponseRedirect, render, get_object_or_404
from django.utils.timezone import utc, make_aware
from django.views.decorators.cache import never_cache

from cl.alerts.forms import CreateAlertForm
from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import naturalduration
from cl.lib.bot_detector import is_bot
from cl.lib.scorched_utils import ExtraSolrInterface, MoreLikeThisHighlightsSolrInterface, MoreLikeThisHighlightsSolrSearch
from cl.lib.search_utils import build_main_query, get_query_citation, \
    make_stats_variable, merge_form_with_courts, make_get_string, \
    regroup_snippets
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
        return True
    return False


def get_mlt_query(cd, facet, solr_url, seed_pk, filter_query):
    """
    By default Solr MoreLikeThis queries do not support highlighting. Thus, we use a special search interface
    and build the Solr query manually.

    :param cd: Cleaned search form data
    :param facet: Set to True to enable facets
    :param solr_url: URL from Solr endpoint, e.g. settings.SOLR_OPINION_URL
    :param seed_pk: ID of the document for that related documents should be returned
    :param filter_query:
    :return: Executed SolrSearch
    """
    si = MoreLikeThisHighlightsSolrInterface(solr_url, mode='r')

    print('Related for #{}, filter query: {}'.format(seed_pk, filter_query))

    # Reset query for query builder
    cd['q'] = ''

    # Build main query as always
    q = build_main_query(cd, facet=facet)

    # Option A: strip field queries, e.g. foo:bar would produce an invalid filter_query
    # Option B: parse original query + validate all field names (not in use)
    cleaned_fq = re.sub('[^-!"()0-9a-zA-Z]+', ' ', filter_query.strip())

    q.update({
        'caller': 'mlt_query',
        'q': 'id:' + seed_pk,
        'mlt': 'true',  # Python boolean does not work here
        'mlt.fl': 'text',

        # Retrieve fields as highlight replacement
        'fl': q['fl'] + ',' + (','.join(MoreLikeThisHighlightsSolrSearch.highlight_fields)),

        # Original query as filter query
        'fq': q['fq'] + [cleaned_fq],

        # unset fields not used for MLT
        'boost': '',
        'pf': '',
        'ps': '',
        'qf': '',
    })

    return si.query().add_extra(**q)


def do_search(request, rows=20, order_by=None, type=None, facet=True):

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
        search_form = _clean_form(request, cd, courts)

        if cd['type'] == 'o':
            # This is a `related:` prefix query?
            related_prefix_match = re.search(r'^related:opinion(?P<pk>[0-9]+)(?P<fq>.*)', cd['q'])
            if related_prefix_match:
                results = get_mlt_query(cd, facet, settings.SOLR_OPINION_URL,
                                        related_prefix_match.group('pk'),
                                        related_prefix_match.group('fq'))

            else:
                # Default search interface
                si = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode='r')
                results = si.query().add_extra(**build_main_query(cd, facet=facet))

            query_citation = get_query_citation(cd)
        elif cd['type'] == 'r':
            si = ExtraSolrInterface(settings.SOLR_RECAP_URL, mode='r')
            results = si.query().add_extra(**build_main_query(cd, facet=facet))
            courts = courts.filter(
                pacer_court_id__isnull=False,
                end_date__isnull=True,
            ).exclude(
                jurisdiction=Court.FEDERAL_BANKRUPTCY_PANEL,
            )
        elif cd['type'] == 'oa':
            si = ExtraSolrInterface(settings.SOLR_AUDIO_URL, mode='r')
            results = si.query().add_extra(**build_main_query(cd, facet=facet))
        elif cd['type'] == 'p':
            si = ExtraSolrInterface(settings.SOLR_PEOPLE_URL, mode='r')
            results = si.query().add_extra(**build_main_query(cd, facet=facet))

        # Run the query and set up pagination
        page = int(request.GET.get('page', 1))
        too_deep = check_pagination_depth(page)
        if too_deep:
            logger.warning("Query depth of %s denied access (probably a "
                           "crawler)", page)
            error = True
        else:
            try:
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
            except Exception as e:
                # Catches any Solr errors, and aborts.
                logger.warning("Error loading pagination on search page with "
                               "request: %s" % request.GET)
                logger.warning("Error was: %s" % e)
                if settings.DEBUG is True:
                    traceback.print_exc()
                error = True

        # Post processing of the results
        regroup_snippets(paged_results)

    else:
        error = True

    courts, court_count_human, court_count = merge_form_with_courts(courts,
                                                                    search_form)
    search_summary_str = search_form.as_text(court_count, court_count_human)
    return {
        'results': paged_results,
        'search_form': search_form,
        'search_summary_str': search_summary_str,
        'courts': courts,
        'court_count_human': court_count_human,
        'court_count': court_count,
        'query_citation': query_citation,
        'facet_fields': make_stats_variable(search_form, paged_results),
        'error': error,
    }


def get_homepage_stats():
    """Get any stats that are displayed on the homepage and return them as a
    dict
    """
    r = redis.StrictRedis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DATABASES['STATS'],
    )
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

            homepage_cache_key = 'homepage-data'
            homepage_dict = cache.get(homepage_cache_key)
            if homepage_dict is not None:
                return render(request, 'homepage.html', homepage_dict)

            # Load the render_dict with good results that can be shown in the
            # "Latest Cases" section
            render_dict.update(do_search(request, rows=5,
                                         order_by='dateFiled desc',
                                         facet=False))
            # Get the results from the oral arguments as well
            oa_dict = do_search(request, rows=5, order_by='dateArgued desc',
                                type='oa', facet=False)
            render_dict.update({'results_oa': oa_dict['results']})
            # But give it a fresh form for the advanced search section
            render_dict.update({'search_form': SearchForm(request.GET)})

            # Get a bunch of stats.
            render_dict.update(get_homepage_stats())

            six_hours = 60 * 60 * 6
            cache.set(homepage_cache_key, render_dict, six_hours)
            return render(request, 'homepage.html', render_dict)
        else:
            # User placed a search or is trying to edit an alert
            if request.GET.get('edit_alert'):
                # They're editing an alert
                if request.user.is_anonymous():
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
        o_cache_key = 'opinion-homepage-results'
        o_results = cache.get(o_cache_key)
        if o_results is None:
            o_results = do_search(request, rows=1, type=obj_type, facet=True)
            six_hours = 60 * 60 * 6
            cache.set(o_cache_key, o_results, six_hours)

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
