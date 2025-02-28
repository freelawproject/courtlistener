from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from asgiref.sync import async_to_sync
from cache_memoize import cache_memoize
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import HttpResponseRedirect, get_object_or_404, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.timezone import make_aware
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from waffle.decorators import waffle_flag

from cl.alerts.forms import CreateAlertForm
from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import naturalduration
from cl.lib.bot_detector import is_bot
from cl.lib.elasticsearch_utils import get_only_status_facets
from cl.lib.ratelimiter import ratelimiter_unsafe_5_per_d
from cl.lib.redis_utils import get_redis_interface
from cl.lib.search_utils import (
    do_es_search,
    make_get_string,
    merge_form_with_courts,
    store_search_query,
)
from cl.lib.types import AuthenticatedHttpRequest
from cl.search.documents import OpinionClusterDocument
from cl.search.forms import SearchForm, _clean_form
from cl.search.models import SEARCH_TYPES, Court, Opinion
from cl.search.tasks import email_search_results
from cl.stats.models import Stat
from cl.stats.utils import tally_stat
from cl.visualizations.models import SCOTUSMap


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


@login_required
@ratelimiter_unsafe_5_per_d
@require_POST
def export_search_results(request: AuthenticatedHttpRequest) -> HttpResponse:
    email_search_results.delay(request.user.pk, request.POST.get("query", ""))
    # TODO: Update the frontend using Htmx to show a message indicating the
    # export of search results is in progress.
    return HttpResponse("It worked.")
