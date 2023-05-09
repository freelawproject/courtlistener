import logging
import traceback
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from cache_memoize import cache_memoize
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import HttpResponseRedirect, get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.timezone import make_aware
from django.views.decorators.cache import never_cache
from requests import RequestException, Session
from scorched.exc import SolrError

from cl.alerts.forms import CreateAlertForm
from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import naturalduration
from cl.lib.bot_detector import is_bot
from cl.lib.ratelimiter import ratelimit_deny_list
from cl.lib.redis_utils import make_redis_interface
from cl.lib.search_utils import (
    add_depth_counts,
    build_main_query,
    get_mlt_query,
    get_query_citation,
    get_solr_interface,
    make_get_string,
    make_stats_variable,
    merge_form_with_courts,
    regroup_snippets,
)
from cl.search.constants import RELATED_PATTERN
from cl.search.forms import SearchForm, _clean_form
from cl.search.models import SEARCH_TYPES, Court, Opinion, OpinionCluster
from cl.stats.models import Stat
from cl.stats.utils import tally_stat
from cl.visualizations.models import SCOTUSMap

logger = logging.getLogger(__name__)


def check_pagination_depth(page_number):
    """Check if the pagination is too deep (indicating a crawler)"""
    max_search_pagination_depth = 100
    if page_number > max_search_pagination_depth:
        logger.warning(
            "Query depth of %s denied access (probably a crawler)",
            page_number,
        )
        raise PermissionDenied


def paginate_cached_solr_results(get_params, cd, results, rows, cache_key):
    # Run the query and set up pagination
    if cache_key is not None:
        paged_results = cache.get(cache_key)
        if paged_results is not None:
            return paged_results

    try:
        page = int(get_params.get("page", 1))
    except ValueError:
        page = 1
    check_pagination_depth(page)

    if cd["type"] in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
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


def do_search(
    get_params, rows=20, override_params=None, facet=True, cache_key=None
):
    """Do all the difficult solr work.

    :param get_params: The request.GET parameters sent by the user. Note that
    this cannot simply be request.GET since that is immutable and
    override_params needs to be able to change this. Instead generally it's
    best to send request.GET.copy().
    :param rows: The number of solr results to request
    :param override_params: A dict with additional or different GET params to
    be sent to solr.
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
    cited_cluster = None
    courts = Court.objects.filter(in_use=True)
    related_cluster_pks = None

    # Add additional or overridden GET parameters
    if override_params:
        get_params.update(override_params)
    search_form = SearchForm(get_params)

    if search_form.is_valid():
        cd = search_form.cleaned_data

        # Do the query, hitting the cache if desired
        with Session() as session:
            try:
                si = get_solr_interface(cd, http_connection=session)
            except NotImplementedError:
                logger.error(
                    "Tried getting solr connection for %s, but it's not "
                    "implemented yet",
                    cd["type"],
                )
                raise

            try:
                # Is this a `related:<pks>` prefix query?
                related_prefix_match = RELATED_PATTERN.search(cd["q"])
                if related_prefix_match:
                    # Seed IDs
                    related_cluster_pks = related_prefix_match.group(
                        "pks"
                    ).split(",")
                    results = get_mlt_query(
                        si,
                        cd.copy(),
                        facet,
                        related_cluster_pks,
                        # Original query
                        cd["q"].replace(related_prefix_match.group("pfx"), ""),
                    )
                else:
                    # Regular search queries
                    results = si.query().add_extra(
                        **build_main_query(cd, facet=facet)
                    )

                paged_results = paginate_cached_solr_results(
                    get_params, cd, results, rows, cache_key
                )
                cited_cluster = add_depth_counts(
                    # Also returns cited cluster if found
                    search_data=cd,
                    search_results=paged_results,
                )
            except (NotImplementedError, RequestException, SolrError) as e:
                error = True
                logger.warning(
                    f"Error loading search page with request: {get_params}"
                )
                logger.warning(f"Error was: {e}")
                if settings.DEBUG is True:
                    traceback.print_exc()

        # A couple special variables for particular search types
        search_form = _clean_form(get_params, cd, courts)
        if cd["type"] in [
            SEARCH_TYPES.OPINION,
            SEARCH_TYPES.RECAP,
            SEARCH_TYPES.DOCKETS,
        ]:
            query_citation = get_query_citation(cd)

        if cd["type"] in [
            SEARCH_TYPES.RECAP,
            SEARCH_TYPES.DOCKETS,
            SEARCH_TYPES.PEOPLE,
        ]:
            # Exclude BAP courts from RECAP, Dockets, and People
            panel_courts = Court.FEDERAL_BANKRUPTCY_PANEL
            courts = courts.exclude(jurisdiction=panel_courts)
        elif cd["type"] in [SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS]:
            # Only use courts with pacer_court_id and no end date in RECAP
            courts = courts.filter(
                pacer_court_id__isnull=False,
                end_date__isnull=True,
            )
    else:
        error = True

    courts, court_count_human, court_count = merge_form_with_courts(
        courts, search_form
    )
    search_summary_str = search_form.as_text(court_count_human)
    search_summary_dict = search_form.as_display_dict(court_count_human)
    related_cluster = (
        OpinionCluster.objects.get(sub_opinions__pk__in=related_cluster_pks)
        if related_cluster_pks
        else None
    )
    return {
        "results": paged_results,
        "facet_fields": make_stats_variable(search_form, paged_results),
        "search_form": search_form,
        "search_summary_str": search_summary_str,
        "search_summary_dict": search_summary_dict,
        "courts": courts,
        "court_count_human": court_count_human,
        "court_count": court_count,
        "query_citation": query_citation,
        "error": error,
        "cited_cluster": cited_cluster,
        "related_cluster": related_cluster,
    }


@cache_memoize(5 * 60)
def get_homepage_stats():
    """Get any stats that are displayed on the homepage and return them as a
    dict
    """
    r = make_redis_interface("STATS")
    ten_days_ago = make_aware(
        datetime.today() - timedelta(days=10), timezone.utc
    )
    last_ten_days = [
        f"api:v3.d:{(date.today() - timedelta(days=x)).isoformat()}.count"
        for x in range(0, 10)
    ]
    homepage_data = {
        "alerts_in_last_ten": Stat.objects.filter(
            name__contains="alerts.sent", date_logged__gte=ten_days_ago
        ).aggregate(Sum("count"))["count__sum"],
        "queries_in_last_ten": Stat.objects.filter(
            name="search.results", date_logged__gte=ten_days_ago
        ).aggregate(Sum("count"))["count__sum"],
        "opinions_in_last_ten": Opinion.objects.filter(
            date_created__gte=ten_days_ago
        ).count(),
        "oral_arguments_in_last_ten": Audio.objects.filter(
            date_created__gte=ten_days_ago
        ).count(),
        "api_in_last_ten": sum(
            [
                int(result)
                for result in r.mget(*last_ten_days)
                if result is not None
            ]
        ),
        "users_in_last_ten": User.objects.filter(
            date_joined__gte=ten_days_ago
        ).count(),
        "days_of_oa": naturalduration(
            Audio.objects.aggregate(Sum("duration"))["duration__sum"],
            as_dict=True,
        )["d"],
        "viz_in_last_ten": SCOTUSMap.objects.filter(
            date_published__gte=ten_days_ago, published=True
        ).count(),
        "visualizations": SCOTUSMap.objects.filter(
            published=True, deleted=False
        )
        .annotate(Count("clusters"))
        .filter(
            # Ensures that we only show good stuff on homepage
            clusters__count__gt=10,
        )
        .order_by("-date_published", "-date_modified", "-date_created")[:1],
        "private": False,  # VERY IMPORTANT!
    }
    return homepage_data


@never_cache
@ratelimit_deny_list
def show_results(request: HttpRequest) -> HttpResponse:
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
    get_string_sans_alert = make_get_string(
        request, ["page", "edit_alert", "show_alert_modal"]
    )
    render_dict = {
        "private": True,
        "get_string": get_string,
        "get_string_sans_alert": get_string_sans_alert,
    }

    if request.method == "POST":
        # The user is trying to save an alert.
        alert_form = CreateAlertForm(request.POST, user=request.user)
        if alert_form.is_valid():
            cd = alert_form.cleaned_data

            # save the alert
            if request.POST.get("edit_alert"):
                # check if the user can edit this, or if they are url hacking
                alert = get_object_or_404(
                    Alert,
                    pk=request.POST.get("edit_alert"),
                    user=request.user,
                )
                alert_form = CreateAlertForm(
                    cd, instance=alert, user=request.user
                )
                alert_form.save()
                action = "edited"
            else:
                alert_form = CreateAlertForm(cd, user=request.user)
                alert = alert_form.save(commit=False)
                alert.user = request.user
                alert.save()

                action = "created"
            messages.add_message(
                request,
                messages.SUCCESS,
                f"Your alert was {action} successfully.",
            )

            # and redirect to the alerts page
            return HttpResponseRedirect(reverse("profile_alerts"))
        else:
            # Invalid form. Do the search again and show them the alert form
            # with the errors
            render_dict.update(do_search(request.GET.copy()))
            render_dict.update({"alert_form": alert_form})
            return TemplateResponse(request, "search.html", render_dict)

    else:
        # Either a search or the homepage
        if len(request.GET) == 0:
            # No parameters --> Homepage.
            if not is_bot(request):
                tally_stat("search.homepage_loaded")

            # Ensure we get nothing from the future.
            mutable_GET = request.GET.copy()  # Makes it mutable
            mutable_GET["filed_before"] = date.today()

            # Load the render_dict with good results that can be shown in the
            # "Latest Cases" section
            render_dict.update(
                do_search(
                    mutable_GET,
                    rows=5,
                    override_params={"order_by": "dateFiled desc"},
                    facet=False,
                    cache_key="homepage-data-o",
                )
            )
            # Get the results from the oral arguments as well
            render_dict.update(
                {
                    "results_oa": do_search(
                        mutable_GET,
                        rows=5,
                        override_params={
                            "order_by": "dateArgued desc",
                            "type": SEARCH_TYPES.ORAL_ARGUMENT,
                        },
                        facet=False,
                        cache_key="homepage-data-oa",
                    )["results"]
                }
            )

            # But give it a fresh form for the advanced search section
            render_dict.update({"search_form": SearchForm(request.GET)})

            # Get a bunch of stats.
            stats = get_homepage_stats()
            render_dict.update(stats)

            return TemplateResponse(request, "homepage.html", render_dict)
        else:
            # User placed a search or is trying to edit an alert
            if request.GET.get("edit_alert"):
                # They're editing an alert
                if request.user.is_anonymous:
                    return HttpResponseRedirect(
                        "{path}?next={next}{encoded_params}".format(
                            path=reverse("sign-in"),
                            next=request.path,
                            encoded_params=quote(
                                f"?{request.GET.urlencode()}"
                            ),
                        )
                    )
                else:
                    alert = get_object_or_404(
                        Alert,
                        pk=request.GET.get("edit_alert"),
                        user=request.user,
                    )
                    alert_form = CreateAlertForm(
                        instance=alert,
                        initial={"query": get_string_sans_alert},
                        user=request.user,
                    )
            else:
                # Just a regular search
                if not is_bot(request):
                    tally_stat("search.results")

                # Create bare-bones alert form.
                alert_form = CreateAlertForm(
                    initial={"query": get_string, "rate": "dly"},
                    user=request.user,
                )

            render_dict.update(do_search(request.GET.copy()))
            # Set the value to the query as a convenience
            alert_form.fields["name"].widget.attrs["value"] = render_dict[
                "search_summary_str"
            ]
            render_dict.update({"alert_form": alert_form})
            return TemplateResponse(request, "search.html", render_dict)


def advanced(request: HttpRequest) -> HttpResponse:
    render_dict = {"private": False}

    # I'm not thrilled about how this is repeating URLs in a view.
    if request.path == reverse("advanced_o"):
        obj_type = SEARCH_TYPES.OPINION
        # Needed b/c of facet values.

        o_results = do_search(
            request.GET.copy(),
            rows=1,
            override_params={"type": obj_type},
            facet=True,
            cache_key="opinion-homepage-results",
        )
        render_dict.update(o_results)
        render_dict["search_form"] = SearchForm({"type": obj_type})
        return TemplateResponse(request, "advanced.html", render_dict)
    else:
        courts = Court.objects.filter(in_use=True)
        if request.path == reverse("advanced_r"):
            obj_type = SEARCH_TYPES.RECAP
            courts = courts.filter(
                pacer_court_id__isnull=False, end_date__isnull=True
            ).exclude(jurisdiction=Court.FEDERAL_BANKRUPTCY_PANEL)
        elif request.path == reverse("advanced_oa"):
            obj_type = SEARCH_TYPES.ORAL_ARGUMENT
        elif request.path == reverse("advanced_p"):
            obj_type = SEARCH_TYPES.PEOPLE
        else:
            raise NotImplementedError(f"Unknown path: {request.path}")

        search_form = SearchForm({"type": obj_type})
        courts, court_count_human, court_count = merge_form_with_courts(
            courts, search_form
        )
        render_dict.update(
            {
                "search_form": search_form,
                "courts": courts,
                "court_count_human": court_count_human,
                "court_count": court_count,
            }
        )
        return TemplateResponse(request, "advanced.html", render_dict)
