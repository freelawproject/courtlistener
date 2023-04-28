import json
import logging
import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.db.models import Count, QuerySet, Sum
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template import loader
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.cache import cache_page
from rest_framework.status import HTTP_429_TOO_MANY_REQUESTS

from cl.audio.models import Audio
from cl.disclosures.models import (
    Agreement,
    Debt,
    FinancialDisclosure,
    Gift,
    Investment,
    NonInvestmentIncome,
    Position,
    Reimbursement,
    SpouseIncome,
)
from cl.donate.utils import get_donation_totals_by_email
from cl.lib.ratelimiter import ratelimiter_unsafe_3_per_m
from cl.people_db.models import Person
from cl.search.forms import SearchForm
from cl.search.models import (
    SOURCES,
    Court,
    Docket,
    OpinionCluster,
    RECAPDocument,
)
from cl.simple_pages.forms import ContactForm

logger = logging.getLogger(__name__)


def about(request: HttpRequest) -> HttpResponse:
    """Loads the about page"""
    return TemplateResponse(request, "about.html", {"private": False})


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
    return TemplateResponse(request, "help/index.html", {"private": False})


def alert_help(request: HttpRequest) -> HttpResponse:
    no_feeds = Court.federal_courts.all_pacer_courts().filter(
        pacer_has_rss_feed=False,
    )
    partial_feeds = (
        Court.federal_courts.all_pacer_courts()
        .filter(pacer_has_rss_feed=True)
        .exclude(pacer_rss_entry_types="all")
    )
    full_feeds = Court.federal_courts.all_pacer_courts().filter(
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
    return TemplateResponse(request, "help/alert_help.html", context)


def donation_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request, "help/donation_help.html", {"private": False}
    )


def delete_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request, "help/delete_account_help.html", {"private": False}
    )


def markdown_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request, "help/markdown_help.html", {"private": False}
    )


def tag_notes_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(request, "help/tags_help.html", {"private": False})


def recap_email_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request, "help/recap_email_help.html", {"private": False}
    )


def broken_email_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "help/broken_email_help.html",
        {"private": True},
    )


def build_court_dicts(courts: QuerySet) -> list[dict[str, str]]:
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


def get_coverage_data_fds() -> dict[str, int]:
    """Get stats on the disclosure data

    Attempt the cache if possible.

    :return: A dict mapping item types to their counts.
    """
    coverage_key = "coverage-data.fd3"
    coverage_data = cache.get(coverage_key)
    if coverage_data is None:
        coverage_data = {
            "disclosures": FinancialDisclosure,
            "investments": Investment,
            "positions": Position,
            "agreements": Agreement,
            "non_investment_income": NonInvestmentIncome,
            "spousal_income": SpouseIncome,
            "reimbursements": Reimbursement,
            "gifts": Gift,
            "debts": Debt,
        }
        # Populate the models
        for k, model in coverage_data.items():
            coverage_data[k] = model.objects.all().count()

        coverage_data["private"] = False
        one_week = 60 * 60 * 24 * 7
        cache.set(coverage_key, coverage_data, one_week)

    return coverage_data


def coverage_fds(request: HttpRequest) -> HttpResponse:
    """The financial disclosure coverage page"""
    coverage_data = get_coverage_data_fds()
    return TemplateResponse(request, "help/coverage_fds.html", coverage_data)


def get_coverage_data_o(request: HttpRequest) -> dict[str, Any]:
    """Get the opinion coverage data

    :param request: The user's request
    :return:
    """
    coverage_cache_key = "coverage-data-v3"
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
            if SOURCES.PUBLIC_RESOURCE in d["source"]:
                count_pro += d["source__count"]
            if SOURCES.COURT_WEBSITE in d["source"]:
                count_scraper += d["source__count"]
            if SOURCES.LAWBOX in d["source"]:
                count_lawbox += d["source__count"]

        opinion_courts = Court.objects.filter(
            in_use=True, has_opinion_scraper=True
        )
        oral_argument_courts = Court.objects.filter(
            in_use=True, has_oral_argument_scraper=True
        )
        count_fds = FinancialDisclosure.objects.all().count()
        count_investments = Investment.objects.all().count()
        count_people = Person.objects.all().count()

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
            "count_fds": count_fds,
            "count_investments": count_investments,
            "count_people": count_people,
            "courts_with_opinion_scrapers": opinion_courts,
            "courts_with_oral_argument_scrapers": oral_argument_courts,
            "private": False,
        }
        one_day = 60 * 60 * 24
        cache.set(coverage_cache_key, coverage_data, one_day)
    return coverage_data


def coverage_graph(request: HttpRequest) -> HttpResponse:
    coverage_data_o = get_coverage_data_o(request)
    return TemplateResponse(request, "help/coverage.html", coverage_data_o)


def feeds(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
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
    return TemplateResponse(
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
    return TemplateResponse(request, "contribute.html", {"private": False})


@ratelimiter_unsafe_3_per_m
def contact(
    request: HttpRequest,
    template_path: str = "contact_form.html",
    template_data: dict[str, ContactForm | str | bool] | None = None,
    initial: dict[str, str] | None = None,
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

            donation_totals = get_donation_totals_by_email(cd["email"])
            default_from = settings.DEFAULT_FROM_EMAIL
            EmailMessage(
                subject="[CourtListener] Contact: "
                "{phone_number}".format(**cd),
                body="Subject: {phone_number}\n"
                "From: {name} ({email})\n"
                "Total donated: {total_donated}\n"
                "Total last year: {total_last_year}\n\n\n"
                "{message}\n\n"
                "Browser: {browser}".format(
                    browser=request.META.get("HTTP_USER_AGENT", "Unknown"),
                    total_donated=donation_totals["total"],
                    total_last_year=donation_totals["last_year"],
                    **cd,
                ),
                to=["info@free.law"],
                reply_to=[cd.get("email", default_from) or default_from],
            ).send()
            return HttpResponseRedirect(reverse("contact_thanks"))
    else:
        # the form is loading for the first time
        if isinstance(request.user, User):
            initial["email"] = request.user.email
            initial["name"] = request.user.get_full_name()
            form = ContactForm(initial=initial)
        else:
            # for anonymous users, who lack full_names, and emails
            form = ContactForm(initial=initial)

    template_data.update({"form": form, "private": False})
    return TemplateResponse(request, template_path, template_data)


def contact_thanks(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(request, "contact_thanks.html", {"private": True})


def advanced_search(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request, "help/advanced_search.html", {"private": False}
    )


def old_terms(request: HttpRequest, v: str) -> HttpResponse:
    return TemplateResponse(
        request,
        f"terms/{v}.html",
        {
            "title": "Archived Terms of Service and Policies, v%s – "
            "CourtListener.com" % v,
            "private": True,
        },
    )


def latest_terms(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "terms/latest.html",
        {
            "title": "Terms of Service and Policies – CourtListener.com",
            "private": False,
        },
    )


@cache_page(60 * 60 * 12, cache="db_cache")
def robots(request: HttpRequest) -> HttpResponse:
    """Generate the robots.txt file"""
    response = HttpResponse(content_type="text/plain")
    t = loader.get_template("robots.txt")
    response.write(t.render({}))
    return response


def validate_for_wot(request: HttpRequest) -> HttpResponse:
    return HttpResponse("bcb982d1e23b7091d5cf4e46826c8fc0")


def ratelimited(request: HttpRequest, exception: Exception) -> HttpResponse:
    return TemplateResponse(
        request,
        "429.html",
        {"private": True},
        status=HTTP_429_TOO_MANY_REQUESTS,
    )
