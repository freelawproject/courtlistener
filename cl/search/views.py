import logging
import pickle
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from asgiref.sync import async_to_sync
from cache_memoize import cache_memoize
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, Page, PageNotAnInteger
from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse
from django.http.request import QueryDict
from django.shortcuts import HttpResponseRedirect, get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.timezone import make_aware
from django.views.decorators.cache import never_cache
from django_elasticsearch_dsl.search import Search
from eyecite.models import FullCaseCitation
from waffle.decorators import waffle_flag

from cl.alerts.forms import CreateAlertForm
from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.citations.match_citations_queries import es_get_query_citation
from cl.custom_filters.templatetags.text_filters import naturalduration
from cl.lib.bot_detector import is_bot
from cl.lib.crypto import sha256
from cl.lib.elasticsearch_utils import (
    build_es_main_query,
    compute_lowest_possible_estimate,
    convert_str_date_fields_to_date_objects,
    fetch_es_results,
    get_facet_dict_for_search_query,
    get_only_status_facets,
    limit_inner_hits,
    merge_courts_from_db,
    merge_unavailable_fields_on_parent_document,
    set_results_highlights,
    simplify_estimated_count,
)
from cl.lib.paginators import ESPaginator
from cl.lib.redis_utils import get_redis_interface
from cl.lib.search_utils import (
    add_depth_counts,
    make_get_string,
    merge_form_with_courts,
    store_search_query,
)
from cl.lib.types import CleanData
from cl.lib.utils import (
    sanitize_unbalanced_parenthesis,
    sanitize_unbalanced_quotes,
)
from cl.search.constants import RELATED_PATTERN
from cl.search.documents import (
    AudioDocument,
    DocketDocument,
    OpinionClusterDocument,
    ParentheticalGroupDocument,
    PersonDocument,
)
from cl.search.exception import (
    BadProximityQuery,
    UnbalancedParenthesesQuery,
    UnbalancedQuotesQuery,
)
from cl.search.forms import SearchForm, _clean_form
from cl.search.models import SEARCH_TYPES, Court, Opinion, OpinionCluster
from cl.stats.models import Stat
from cl.stats.utils import tally_stat
from cl.visualizations.models import SCOTUSMap

logger = logging.getLogger(__name__)


def check_pagination_depth(page_number):
    """Check if the pagination is too deep (indicating a crawler)"""

    if page_number > settings.MAX_SEARCH_PAGINATION_DEPTH:
        logger.warning(
            "Query depth of %s denied access (probably a crawler)",
            page_number,
        )
        raise PermissionDenied


@cache_memoize(5 * 60)
def get_homepage_stats():
    """Get any stats that are displayed on the homepage and return them as a
    dict
    """
    r = get_redis_interface("STATS")
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
            render_dict.update(do_es_search(request.GET.copy()))
            render_dict.update({"alert_form": alert_form})
            return TemplateResponse(request, "search.html", render_dict)

    # This is a GET request: Either a search or the homepage
    if len(request.GET) == 0:
        # No parameters --> Homepage.
        if not is_bot(request):
            async_to_sync(tally_stat)("search.homepage_loaded")

        # Ensure we get nothing from the future.
        mutable_GET = request.GET.copy()  # Makes it mutable
        mutable_GET["filed_before"] = date.today()

        # Load the render_dict with good results that can be shown in the
        # "Latest Opinions" section
        mutable_GET.update(
            {
                "order_by": "dateFiled desc",
                "type": SEARCH_TYPES.OPINION,
            }
        )
        search = do_es_search(
            mutable_GET,
            rows=5,
            facet=False,
            cache_key="homepage-data-o-es",
        )

        render_dict.update(**search)
        # Rename dictionary key "results" to "results_o" for consistency.
        render_dict["results_o"] = render_dict.pop("results")

        # Get the results from the oral arguments as well
        # Add additional or overridden GET parameters
        mutable_GET.update(
            {
                "order_by": "dateArgued desc",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
            }
        )
        render_dict.update(
            {
                "results_oa": do_es_search(
                    mutable_GET,
                    rows=5,
                    facet=False,
                    cache_key="homepage-data-oa-es",
                )["results"]
            }
        )

        # But give it a fresh form for the advanced search section
        render_dict.update({"search_form": SearchForm(request.GET)})

        # Get a bunch of stats.
        stats = get_homepage_stats()
        render_dict.update(stats)

        return TemplateResponse(request, "homepage.html", render_dict)

    # This is a GET with parameters
    # User placed a search or is trying to edit an alert
    if request.GET.get("edit_alert"):
        # They're editing an alert
        if request.user.is_anonymous:
            return HttpResponseRedirect(
                "{path}?next={next}{encoded_params}".format(
                    path=reverse("sign-in"),
                    next=request.path,
                    encoded_params=quote(f"?{request.GET.urlencode()}"),
                )
            )

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
            async_to_sync(tally_stat)("search.results")

        # Create bare-bones alert form.
        alert_form = CreateAlertForm(
            initial={
                "query": get_string,
                "rate": "dly",
                "alert_type": request.GET.get("type", SEARCH_TYPES.OPINION),
            },
            user=request.user,
        )

    search_results = do_es_search(request.GET.copy())
    render_dict.update(search_results)
    store_search_query(request, search_results)

    # Set the value to the query as a convenience
    alert_form.fields["name"].widget.attrs["value"] = render_dict[
        "search_summary_str"
    ]
    render_dict.update({"alert_form": alert_form})

    return TemplateResponse(request, "search.html", render_dict)


@never_cache
def advanced(request: HttpRequest) -> HttpResponse:
    render_dict = {"private": False}

    # I'm not thrilled about how this is repeating URLs in a view.
    if request.path == reverse("advanced_o"):
        courts = Court.objects.filter(in_use=True)
        obj_type = SEARCH_TYPES.OPINION
        search_form = SearchForm({"type": obj_type}, courts=courts)
        render_dict["search_form"] = search_form
        # Needed b/c of facet values.
        search_query = OpinionClusterDocument.search()
        facet_results = get_only_status_facets(
            search_query, render_dict["search_form"]
        )
        search_form.is_valid()
        cd = search_form.cleaned_data
        search_form = _clean_form({"type": obj_type}, cd, courts)
        # Merge form with courts.
        courts, court_count_human, court_count = merge_form_with_courts(
            courts, search_form
        )
        render_dict.update(
            {
                "facet_fields": facet_results,
                "courts": courts,
                "court_count_human": court_count_human,
                "court_count": court_count,
            }
        )
        return TemplateResponse(request, "advanced.html", render_dict)
    else:
        courts = courts_in_use = Court.objects.filter(in_use=True)
        if request.path == reverse("advanced_r"):
            obj_type = SEARCH_TYPES.RECAP
            courts_in_use = courts.filter(
                pacer_court_id__isnull=False, end_date__isnull=True
            ).exclude(jurisdiction=Court.FEDERAL_BANKRUPTCY_PANEL)
        elif request.path == reverse("advanced_oa"):
            obj_type = SEARCH_TYPES.ORAL_ARGUMENT
        elif request.path == reverse("advanced_p"):
            obj_type = SEARCH_TYPES.PEOPLE
        else:
            raise NotImplementedError(f"Unknown path: {request.path}")

        search_form = SearchForm({"type": obj_type}, courts=courts)
        courts, court_count_human, court_count = merge_form_with_courts(
            courts_in_use, search_form
        )
        render_dict.update(
            {
                "search_form": search_form,
                "courts": courts,
                "court_count_human": court_count_human,
                "court_count": court_count,
            }
        )
        return render(request, "advanced.html", render_dict)


@waffle_flag("parenthetical-search")
def es_search(request: HttpRequest) -> HttpResponse:
    """Display elasticsearch search page based on type passed as url param
    :param request: HttpRequest object
    :return: HttpResponse
    """
    render_dict = {"private": False}
    courts = Court.objects.filter(in_use=True)
    render_dict.update({"search_type": "parenthetical"})
    obj_type = SEARCH_TYPES.PARENTHETICAL
    search_form = SearchForm({"type": obj_type}, courts=courts)
    if search_form.is_valid():
        search_form = _clean_form(
            request.GET.copy(), search_form.cleaned_data, courts
        )
    template = "advanced.html"

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

    return render(request, template, render_dict)


def remove_missing_citations(
    missing_citations: list[FullCaseCitation], cd: CleanData
) -> tuple[list[str], str]:
    """Removes missing citations from the query and returns the missing
    citations as strings and the modified query.

    :param missing_citations: A list of FullCaseCitation objects representing
    the citations that are missing from the query.
    :param cd: A CleanData object containing the query string.
    :return: A two-tuple containing a list of missing citation strings and the
    suggested query string with missing citations removed.
    """
    missing_citations_str = [
        citation.corrected_citation() for citation in missing_citations
    ]
    query_string = cd["q"]
    for citation in missing_citations_str:
        query_string = query_string.replace(citation, "")
    suggested_query = (
        " ".join(query_string.split()) if missing_citations_str else ""
    )
    return missing_citations_str, suggested_query


def do_es_search(
    get_params: QueryDict,
    rows: int = settings.SEARCH_PAGE_SIZE,
    facet: bool = True,
    cache_key: str = None,
):
    """Run Elasticsearch searching and filtering and prepare data to display

    :param get_params: The request.GET params sent by user.
    :param rows: The number of Elasticsearch results to request
    :param facet: Whether to complete faceting in the query
    :param cache_key: A cache key with which to save the results. Note that it
    does not do anything clever with the actual query, so if you use this, your
    cache key should *already* have factored in the query. If None, no caching
    is set or used. Results are saved for six hours.
    :return: A big dict of variables for use in the search results, homepage, or
    other location.
    """
    paged_results = None
    courts = Court.objects.filter(in_use=True)
    query_time = total_query_results = 0
    top_hits_limit = 5
    document_type = None
    error_message = ""
    suggested_query = ""
    total_child_results = 0
    related_cluster = None
    cited_cluster = None
    query_citation = None
    facet_fields = []
    missing_citations_str = []
    error = True

    search_form = SearchForm(get_params, courts=courts)
    match get_params.get("type", SEARCH_TYPES.OPINION):
        case SEARCH_TYPES.PARENTHETICAL:
            document_type = ParentheticalGroupDocument
        case SEARCH_TYPES.ORAL_ARGUMENT:
            document_type = AudioDocument
        case SEARCH_TYPES.PEOPLE:
            document_type = PersonDocument
        case SEARCH_TYPES.RECAP | SEARCH_TYPES.DOCKETS:
            document_type = DocketDocument
            # Set a different number of results per page for RECAP SEARCH
            rows = settings.RECAP_SEARCH_PAGE_SIZE
        case SEARCH_TYPES.OPINION:
            document_type = OpinionClusterDocument

    if search_form.is_valid() and document_type:
        # Copy cleaned_data to preserve the original data when displaying the form
        cd = search_form.cleaned_data.copy()
        try:
            # Create necessary filters to execute ES query
            search_query = document_type.search()

            if cd["type"] in [
                SEARCH_TYPES.OPINION,
                SEARCH_TYPES.RECAP,
                SEARCH_TYPES.DOCKETS,
            ]:
                query_citation, missing_citations = es_get_query_citation(cd)
                if cd["type"] in [
                    SEARCH_TYPES.OPINION,
                ]:
                    missing_citations_str, suggested_query = (
                        remove_missing_citations(missing_citations, cd)
                    )
                    cd["q"] = suggested_query if suggested_query else cd["q"]
            (
                s,
                child_docs_count_query,
                top_hits_limit,
            ) = build_es_main_query(search_query, cd)
            (
                paged_results,
                query_time,
                error,
                total_query_results,
                total_child_results,
            ) = fetch_and_paginate_results(
                get_params,
                s,
                child_docs_count_query,
                rows_per_page=rows,
                cache_key=cache_key,
            )
            cited_cluster = async_to_sync(add_depth_counts)(
                # Also returns cited cluster if found
                search_data=cd,
                search_results=paged_results,
            )
            related_prefix = RELATED_PATTERN.search(cd["q"])
            if related_prefix:
                related_pks = related_prefix.group("pks").split(",")
                related_cluster = OpinionCluster.objects.filter(
                    sub_opinions__pk__in=related_pks
                ).distinct("pk")
        except UnbalancedParenthesesQuery as e:
            error = True
            error_message = "unbalanced_parentheses"
            if e.error_type == UnbalancedParenthesesQuery.QUERY_STRING:
                suggested_query = sanitize_unbalanced_parenthesis(
                    cd.get("q", "")
                )
        except UnbalancedQuotesQuery as e:
            error = True
            error_message = "unbalanced_quotes"
            if e.error_type == UnbalancedParenthesesQuery.QUERY_STRING:
                suggested_query = sanitize_unbalanced_quotes(cd.get("q", ""))
        except BadProximityQuery as e:
            error = True
            error_message = "bad_proximity_token"
            suggested_query = "proximity_filter"
            if e.error_type == UnbalancedParenthesesQuery.QUERY_STRING:
                suggested_query = "proximity_query"
        finally:
            # Make sure to always call the _clean_form method
            search_form = _clean_form(
                get_params, search_form.cleaned_data, courts
            )
            if cd["type"] in [SEARCH_TYPES.OPINION] and facet:
                # If the search query is valid, pass the cleaned data to filter and
                # retrieve the correct number of opinions per status. Otherwise (if
                # the query has errors), just provide a dictionary containing the
                # search type to get the total number of opinions per status
                facet_fields = get_facet_dict_for_search_query(
                    search_query,
                    cd if not error else {"type": cd["type"]},
                    search_form,
                )

    courts, court_count_human, court_count = merge_form_with_courts(
        courts, search_form
    )
    search_summary_str = search_form.as_text(court_count_human)
    search_summary_dict = search_form.as_display_dict(court_count_human)
    results_details = [
        query_time,
        total_query_results,
        top_hits_limit,
        total_child_results,
    ]

    return {
        "results": paged_results,
        "results_details": results_details,
        "search_form": search_form,
        "search_summary_str": search_summary_str,
        "search_summary_dict": search_summary_dict,
        "error": error,
        "courts": courts,
        "court_count_human": court_count_human,
        "court_count": court_count,
        "query_citation": query_citation,
        "cited_cluster": cited_cluster,
        "related_cluster": related_cluster,
        "facet_fields": facet_fields,
        "error_message": error_message,
        "suggested_query": suggested_query,
        "estimated_count_threshold": simplify_estimated_count(
            compute_lowest_possible_estimate(
                settings.ELASTICSEARCH_CARDINALITY_PRECISION
            )
        ),
        "missing_citations": missing_citations_str,
    }


def retrieve_cached_search_results(
    get_params: QueryDict,
) -> tuple[dict[str, Page | int] | None, str]:
    """
    Retrieve cached search results based on the GET parameters.

    :param get_params: The GET parameters provided by the user.
    :return: A two-tuple containing either the cached search results and the
    cache key based ona prefix and the get parameters, or None and the cache key
    if no cached results were found.
    """

    params = get_params.copy()
    # If no page is present in the parameters, set it to 1 to generate the same
    # hash for page 1, regardless of whether the page parameter is included.
    # Apply the same to the q parameter when it is not present in params.
    params.setdefault("page", "1")
    params.setdefault("q", "")
    sorted_params = dict(sorted(params.items()))
    key_prefix = "search_results_cache:"
    params_hash = sha256(pickle.dumps(sorted_params))
    cache_key = f"{key_prefix}{params_hash}"
    cached_results = cache.get(cache_key)
    if cached_results:
        return pickle.loads(cached_results), cache_key
    return None, cache_key


def fetch_and_paginate_results(
    get_params: QueryDict,
    search_query: Search,
    child_docs_count_query: Search | None,
    rows_per_page: int = settings.SEARCH_PAGE_SIZE,
    cache_key: str = None,
) -> tuple[Page | list, int, bool, int | None, int | None]:
    """Fetch and paginate elasticsearch results.

    :param get_params: The user get params.
    :param search_query: Elasticsearch DSL Search object
    :param child_docs_count_query: The ES DSL Query to perform the count for
    child documents if required, otherwise None.
    :param rows_per_page: Number of records wanted per page
    :param cache_key: The cache key to use.
    :return: A five-tuple: the paginated results, the ES query time, whether
    there was an error, the total number of hits for the main document, and
    the total number of hits for the child document.
    """

    # Run the query and set up pagination
    if cache_key is not None:
        # Check cache for displaying insights on the Home Page.
        results = cache.get(cache_key)
        if results is not None:
            return results, 0, False, None, None

    # Check micro-cache for all other search requests.
    results_dict, micro_cache_key = retrieve_cached_search_results(get_params)
    if results_dict:
        # Return results and counts. Set query time to 1ms.
        return (
            results_dict["results"],
            1,
            False,
            results_dict["main_total"],
            results_dict["child_total"],
        )

    try:
        page = int(get_params.get("page", 1))
    except ValueError:
        page = 1

    # Check pagination depth
    check_pagination_depth(page)

    # Fetch results from ES
    hits, query_time, error, main_total, child_total = fetch_es_results(
        get_params, search_query, child_docs_count_query, page, rows_per_page
    )

    if error:
        return [], query_time, error, main_total, child_total
    paginator = ESPaginator(main_total, hits, rows_per_page)
    try:
        results = paginator.page(page)
    except PageNotAnInteger:
        results = paginator.page(1)
    except EmptyPage:
        results = paginator.page(paginator.num_pages)

    search_type = get_params.get("type", SEARCH_TYPES.OPINION)
    # Set highlights in results.
    convert_str_date_fields_to_date_objects(results, search_type)
    merge_courts_from_db(results, search_type)
    limit_inner_hits(get_params, results, search_type)
    set_results_highlights(results, search_type)
    merge_unavailable_fields_on_parent_document(results, search_type)

    if cache_key is not None:
        # Cache only Page results for displaying insights on the Home Page.
        cache.set(cache_key, results, settings.QUERY_RESULTS_CACHE)
    elif settings.ELASTICSEARCH_MICRO_CACHE_ENABLED:
        # Cache Page results and counts for all other search requests.
        results_dict = {
            "results": results,
            "main_total": main_total,
            "child_total": child_total,
        }
        serialized_data = pickle.dumps(results_dict)
        cache.set(
            micro_cache_key,
            serialized_data,
            settings.SEARCH_RESULTS_MICRO_CACHE,
        )

    return results, query_time, error, main_total, child_total
