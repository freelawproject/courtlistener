import json
import logging
import os
import re
from datetime import timedelta
from typing import Union, Dict, List, Optional
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.urls import reverse
from django.db.models import Count, Sum, QuerySet
from django.http import HttpResponse, HttpRequest
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.template import loader
from django.utils.timezone import now
from django.views.decorators.cache import cache_page
from rest_framework.status import HTTP_429_TOO_MANY_REQUESTS

from cl.audio.models import Audio
from cl.custom_filters.decorators import check_honeypot
from cl.lib.bot_detector import is_og_bot
from cl.lib.decorators import track_in_matomo
from cl.lib.ratelimiter import ratelimiter_unsafe_1_per_m
from cl.opinion_page.views import view_recap_document
from cl.people_db.models import Person
from cl.search.forms import SearchForm
from cl.search.models import (
    Court,
    OpinionCluster,
    Opinion,
    RECAPDocument,
    Docket,
)
from cl.simple_pages.forms import ContactForm

logger = logging.getLogger(__name__)


def about(request: HttpRequest) -> HttpResponse:
    """Loads the about page"""
    return render(request, "about.html", {"private": False})


def faq(request: HttpRequest) -> HttpResponse:
    """Loads the FAQ page"""
    faq_cache_key = "faq-stats"
    template_data = cache.get(faq_cache_key)
    if template_data is None:
        template_data = {
            "scraped_court_count": Court.objects.filter(
                in_use=True, has_opinion_scraper=True
            ).count(),
            "total_opinion_count": OpinionCluster.objects.all().count(),
            "total_recap_count": RECAPDocument.objects.filter(
                is_available=True
            ).count(),
            "total_oa_minutes": (
                Audio.objects.aggregate(Sum("duration"))["duration__sum"] or 0
            )
            / 60,
            "total_judge_count": Person.objects.all().count(),
        }
        five_days = 60 * 60 * 24 * 5
        cache.set(faq_cache_key, template_data, five_days)

    return contact(
        request,
        template_path="faq.html",
        template_data=template_data,
        initial={"subject": "FAQs"},
    )


def help_home(request: HttpRequest) -> HttpResponse:
    return render(request, "help/index.html", {"private": False})


def alert_help(request: HttpRequest) -> HttpResponse:
    no_feeds = Court.federal_courts.district_pacer_courts().filter(
        pacer_has_rss_feed=False,
    )
    partial_feeds = (
        Court.federal_courts.district_pacer_courts()
        .filter(pacer_has_rss_feed=True)
        .exclude(pacer_rss_entry_types="all")
    )
    full_feeds = Court.federal_courts.district_pacer_courts().filter(
        pacer_has_rss_feed=True, pacer_rss_entry_types="all"
    )
    cache_key = "alert-help-stats"
    data = cache.get(cache_key)
    if data is None:
        data = {
            "d_update_count": Docket.objects.filter(
                date_modified__gte=now() - timedelta(days=1)
            ).count(),
            "de_update_count": RECAPDocument.objects.filter(
                date_modified__gte=now() - timedelta(days=1)
            ).count(),
        }
        one_day = 60 * 60 * 24
        cache.set(cache_key, data, one_day)
    context = {
        "no_feeds": no_feeds,
        "partial_feeds": partial_feeds,
        "full_feeds": full_feeds,
        "private": False,
    }
    context.update(data)
    return render(request, "help/alert_help.html", context)


def donation_help(request: HttpRequest) -> HttpResponse:
    return render(request, "help/donation_help.html", {"private": False})


def delete_help(request: HttpRequest) -> HttpResponse:
    return render(request, "help/delete_account_help.html", {"private": False})


def markdown_help(request: HttpRequest) -> HttpResponse:
    return render(request, "help/markdown_help.html", {"private": False})


def build_court_dicts(courts: QuerySet) -> List[Dict[str, Union[str, int]]]:
    """Takes the court objects, and manipulates them into a list of more useful
    dictionaries"""
    court_dicts = [{"pk": "all", "short_name": "All Courts"}]
    court_dicts.extend(
        [
            {"pk": court.pk, "short_name": court.full_name}
            #'notes': court.notes}
            for court in courts
        ]
    )
    return court_dicts


def coverage_graph(request: HttpRequest) -> HttpResponse:
    coverage_cache_key = "coverage-data-v2"
    coverage_data = cache.get(coverage_cache_key)
    if coverage_data is None:
        courts = Court.objects.filter(in_use=True)
        courts_json = json.dumps(build_court_dicts(courts))

        search_form = SearchForm(request.GET)
        precedential_statuses = [
            field
            for field in search_form.fields.keys()
            if field.startswith("stat_")
        ]

        # Build up the sourcing stats.
        counts = OpinionCluster.objects.values("source").annotate(
            Count("source")
        )
        count_pro = 0
        count_lawbox = 0
        count_scraper = 0
        for d in counts:
            if "R" in d["source"]:
                count_pro += d["source__count"]
            if "C" in d["source"]:
                count_scraper += d["source__count"]
            if "L" in d["source"]:
                count_lawbox += d["source__count"]

        opinion_courts = Court.objects.filter(
            in_use=True, has_opinion_scraper=True
        )
        oral_argument_courts = Court.objects.filter(
            in_use=True, has_oral_argument_scraper=True
        )

        oa_duration = Audio.objects.aggregate(Sum("duration"))["duration__sum"]
        if oa_duration:
            oa_duration /= 60  # Avoids a "unsupported operand type" error

        coverage_data = {
            "sorted_courts": courts_json,
            "precedential_statuses": precedential_statuses,
            "oa_duration": oa_duration,
            "count_pro": count_pro,
            "count_lawbox": count_lawbox,
            "count_scraper": count_scraper,
            "courts_with_opinion_scrapers": opinion_courts,
            "courts_with_oral_argument_scrapers": oral_argument_courts,
            "private": False,
        }
        one_day = 60 * 60 * 24
        cache.set(coverage_cache_key, coverage_data, one_day)

    return render(request, "coverage.html", coverage_data)


def feeds(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "feeds.html",
        {
            "opinion_courts": Court.objects.filter(
                in_use=True, has_opinion_scraper=True
            ),
            "private": False,
        },
    )


def podcasts(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "podcasts.html",
        {
            "oral_argument_courts": Court.objects.filter(
                in_use=True, has_oral_argument_scraper=True
            ),
            "count": Audio.objects.all().count(),
            "private": False,
        },
    )


def contribute(request: HttpRequest) -> HttpResponse:
    return render(request, "contribute.html", {"private": False})


@ratelimiter_unsafe_1_per_m
@check_honeypot(field_name="skip_me_if_alive")
def contact(
    request: HttpRequest,
    template_path: str = "contact_form.html",
    template_data: Optional[Dict[str, str]] = None,
    initial: Optional[Dict[str, str]] = None,
) -> HttpResponse:
    """This is a fairly run-of-the-mill contact form, except that it can be
    overridden in various ways so that its logic can be called from other
    functions.

    We also use a field called phone_number in place of the subject field to
    defeat spam.
    """
    if template_data is None:
        template_data = {}
    if initial is None:
        initial = {}

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            # Uses phone_number as Subject field to defeat spam. If this field
            # begins with three digits, assume it's spam; fake success.
            if re.match(r"\d{3}", cd["phone_number"]):
                logger.info("Detected spam message. Not sending email.")
                return HttpResponseRedirect(reverse("contact_thanks"))

            default_from = settings.DEFAULT_FROM_EMAIL
            EmailMessage(
                subject="[CourtListener] Contact: "
                "{phone_number}".format(**cd),
                body="Subject: {phone_number}\n"
                "From: {name} ({email})\n"
                "\n\n{message}\n\n"
                "Browser: {browser}".format(
                    browser=request.META.get("HTTP_USER_AGENT", "Unknown"),
                    **cd
                ),
                to=["info@free.law"],
                reply_to=[cd.get("email", default_from) or default_from],
            ).send()
            return HttpResponseRedirect(reverse("contact_thanks"))
    else:
        # the form is loading for the first time
        try:
            initial["email"] = request.user.email
            initial["name"] = request.user.get_full_name()
            form = ContactForm(initial=initial)
        except AttributeError:
            # for anonymous users, who lack full_names, and emails
            form = ContactForm(initial=initial)

    template_data.update({"form": form, "private": False})
    return render(request, template_path, template_data)


def contact_thanks(request: HttpRequest) -> HttpResponse:
    return render(request, "contact_thanks.html", {"private": True})


def advanced_search(request: HttpRequest) -> HttpResponse:
    return render(request, "advanced_search.html", {"private": False})


def old_terms(request: HttpRequest, v: str) -> HttpResponse:
    return render(
        request,
        "terms/%s.html" % v,
        {
            "title": "Archived Terms of Service and Policies, v%s – "
            "CourtListener.com" % v,
            "private": True,
        },
    )


def latest_terms(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "terms/latest.html",
        {
            "title": "Terms of Service and Policies – CourtListener.com",
            "private": False,
        },
    )


@cache_page(60 * 60 * 6)
def robots(request: HttpRequest) -> HttpResponse:
    """Generate the robots.txt file"""
    response = HttpResponse(content_type="text/plain")
    t = loader.get_template("robots.txt")
    # This is sloppy. We take the current moment, in UTC, subtract hours from
    # it, then use it to query a date field in the DB. We could use fewer hours
    # here if we had a datetime in the DB instead, but we have to go a little
    # bigger here to make sure items are on robots.txt long enough.
    block_threshold = now() - timedelta(hours=24 * 5)
    blocked_dockets = Docket.objects.filter(
        date_blocked__gt=block_threshold
    ).exclude(date_created__gt=block_threshold)
    blocked_opinions = OpinionCluster.objects.filter(
        date_blocked__gt=block_threshold
    )
    blocked_afs = Audio.objects.filter(date_blocked__gt=block_threshold)
    response.write(
        t.render(
            {
                "blocked_dockets": blocked_dockets,
                "blocked_opinions": blocked_opinions,
                "blocked_afs": blocked_afs,
            }
        )
    )
    return response


def validate_for_wot(request: HttpRequest) -> HttpResponse:
    return HttpResponse("bcb982d1e23b7091d5cf4e46826c8fc0")


def ratelimited(request: HttpRequest, exception: Exception) -> HttpResponse:
    return render(
        request,
        "429.html",
        {"private": True},
        status=HTTP_429_TOO_MANY_REQUESTS,
    )


@track_in_matomo(timeout=0.01)
def serve_static_file(
    request: HttpRequest,
    file_path: str = "",
) -> HttpResponse:
    """Serve a recap file or redirect to HTML if it's a bot.

    Use nginx's X-Accel system to set headers without putting files in memory.
    """
    # If it's a open graph crawler, serve the HTML page so they can get
    # thumbnails instead of serving the PDF binary.
    og_disabled = bool(request.GET.get("no-og"))
    if is_og_bot(request) and not og_disabled:
        # Serve up the regular HTML page, which has the twitter card info.
        try:
            rd = RECAPDocument.objects.get(filepath_local=file_path)
        except (
            RECAPDocument.DoesNotExist,
            RECAPDocument.MultipleObjectsReturned,
        ):
            # Fall through; serve it normally.
            pass
        else:
            return view_recap_document(
                request,
                docket_id=rd.docket_entry.docket_id,
                doc_num=rd.document_number,
                att_num=rd.attachment_number,
            )

    response = HttpResponse()
    response["Content-Type"] = "application/pdf"

    file_name = file_path.split("/")[-1]

    # HTTP headers didn't get encoding figured out until recently. As a result
    # content disposition headers are a mess. Luckily, we can steal the junk
    # below from Django.
    try:
        # Try with ascii. If it works, do it.
        file_name.encode("ascii")
        file_expr = 'filename="{}"'.format(file_name)
    except UnicodeEncodeError:
        # Ascii failed. Do utf-8 params.
        file_expr = "filename*=utf-8''{}".format(quote(file_name))
    response["Content-Disposition"] = "inline; %s" % file_expr

    # Use microcache for RECAP PDFs. This should help with traffic bursts.
    response["X-Accel-Expires"] = "5"
    # Block all RECAP PDFs
    response["X-Robots-Tag"] = "noindex, noodp, noarchive, noimageindex"

    if settings.DEVELOPMENT:
        # X-Accel-Redirect will only confuse you in a dev env.
        file_loc = os.path.join(settings.MEDIA_ROOT, file_path)
        with open(file_loc, "rb") as f:
            response.content = f.read()
    else:
        file_loc = os.path.join("/protected/", file_path)
        response["X-Accel-Redirect"] = file_loc

    return response
