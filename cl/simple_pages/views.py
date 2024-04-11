import json
import logging
import re
from datetime import timedelta
from http import HTTPStatus
from typing import Any

from asgiref.sync import sync_to_async
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
from cl.people_db.models import Person
from cl.search.models import (
    SOURCES,
    Court,
    Docket,
    OpinionCluster,
    RECAPDocument,
)
from cl.simple_pages.coverage_utils import fetch_data, fetch_federal_data
from cl.simple_pages.forms import ContactForm

logger = logging.getLogger(__name__)


async def about(request: HttpRequest) -> HttpResponse:
    """Loads the about page"""
    return TemplateResponse(request, "about.html", {"private": False})


async def faq(request: HttpRequest) -> HttpResponse:
    """Loads the FAQ page"""
    faq_cache_key = "faq-stats"
    template_data = await cache.aget(faq_cache_key)
    if template_data is None:
        template_data = {
            "scraped_court_count": await Court.objects.filter(
                in_use=True, has_opinion_scraper=True
            ).acount(),
            "total_opinion_count": await OpinionCluster.objects.all().acount(),
            "total_recap_count": await RECAPDocument.objects.filter(
                is_available=True
            ).acount(),
            "total_oa_minutes": (
                (await Audio.objects.aaggregate(Sum("duration")))[
                    "duration__sum"
                ]
                or 0
            )
            / 60,
            "total_judge_count": await Person.objects.all().acount(),
        }
        five_days = 60 * 60 * 24 * 5
        await cache.aset(faq_cache_key, template_data, five_days)

    return await contact(
        request,
        template_path="faq.html",
        template_data=template_data,
        initial={"subject": "FAQs"},
    )


async def help_home(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(request, "help/index.html", {"private": False})


async def alert_help(request: HttpRequest) -> HttpResponse:
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
    data = await cache.aget(cache_key)
    if data is None:
        data = {
            "d_update_count": await Docket.objects.filter(
                date_modified__gte=now() - timedelta(days=1)
            ).acount(),
            "de_update_count": await RECAPDocument.objects.filter(
                date_modified__gte=now() - timedelta(days=1)
            ).acount(),
        }
        one_day = 60 * 60 * 24
        await cache.aset(cache_key, data, one_day)
    context = {
        "no_feeds": no_feeds,
        "partial_feeds": partial_feeds,
        "full_feeds": full_feeds,
        "private": False,
    }
    context.update(data)
    return TemplateResponse(request, "help/alert_help.html", context)


async def delete_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request, "help/delete_account_help.html", {"private": False}
    )


async def markdown_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request, "help/markdown_help.html", {"private": False}
    )


async def tag_notes_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(request, "help/tags_help.html", {"private": False})


async def recap_email_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request, "help/recap_email_help.html", {"private": False}
    )


async def broken_email_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "help/broken_email_help.html",
        {"private": True},
    )


async def build_court_dicts(courts: QuerySet) -> list[dict[str, str]]:
    """Takes the court objects, and manipulates them into a list of more useful
    dictionaries"""
    court_dicts = [{"pk": "all", "short_name": "All Courts"}]
    court_dicts.extend(
        [
            {"pk": court.pk, "short_name": court.full_name}
            async for court in courts
        ]
    )
    return court_dicts


async def get_coverage_data_fds() -> dict[str, int]:
    """Get stats on the disclosure data

    Attempt the cache if possible.

    :return: A dict mapping item types to their counts.
    """
    coverage_key = "coverage-data.fd3"
    coverage_data = await cache.aget(coverage_key)
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
            coverage_data[k] = await model.objects.all().acount()

        coverage_data["private"] = False
        one_week_minutes = 60 * 60 * 24 * 7
        await cache.aset(coverage_key, coverage_data, one_week_minutes)

    return coverage_data


async def coverage_fds(request: HttpRequest) -> HttpResponse:
    """The financial disclosure coverage page"""
    coverage_data = await get_coverage_data_fds()
    return TemplateResponse(request, "help/coverage_fds.html", coverage_data)


async def get_coverage_data_o(request: HttpRequest) -> dict[str, Any]:
    """Get the opinion coverage data

    :param request: The user's request
    :return:
    """
    coverage_cache_key = "coverage-data-v3"
    coverage_data = await cache.aget(coverage_cache_key)
    if coverage_data is None:
        courts = Court.objects.filter(in_use=True)
        courts_json = json.dumps(await build_court_dicts(courts))
        # Build up the sourcing stats.
        counts = OpinionCluster.objects.values("source").annotate(
            Count("source")
        )
        count_pro = 0
        count_lawbox = 0
        count_scraper = 0
        async for d in counts:
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
        count_fds = await FinancialDisclosure.objects.all().acount()
        count_investments = await Investment.objects.all().acount()
        count_people = await Person.objects.all().acount()

        oa_aggregate = await Audio.objects.aaggregate(Sum("duration"))
        oa_duration = oa_aggregate["duration__sum"]
        if oa_duration:
            oa_duration /= 60  # Avoids a "unsupported operand type" error

        coverage_data = {
            "sorted_courts": courts_json,
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
        await cache.aset(coverage_cache_key, coverage_data, one_day)
    return coverage_data


async def coverage(request: HttpRequest) -> HttpResponse:
    coverage_data_o = await get_coverage_data_o(request)
    return TemplateResponse(request, "help/coverage.html", coverage_data_o)


async def coverage_opinions(request: HttpRequest) -> HttpResponse:
    """Generate Coverage Opinion Page

    :param request: A django request
    :return: The page requested
    """
    coverage_data_op = await cache.aget("coverage_data_op")
    if coverage_data_op is None:
        coverage_data_op = {
            "private": False,
            "federal": await fetch_federal_data(),
            "sections": {
                "state": await fetch_data(Court.STATE_JURISDICTIONS),
                "territory": await fetch_data(Court.TERRITORY_JURISDICTIONS),
                "international": await fetch_data(
                    Court.INTERNATIONAL, group_by_state=False
                ),
                "tribal": await fetch_data(
                    Court.TRIBAL_JURISDICTIONS, group_by_state=False
                ),
                "special": await fetch_data(
                    [Court.FEDERAL_SPECIAL], group_by_state=False
                ),
                "military": await fetch_data(
                    Court.MILITARY_JURISDICTIONS, group_by_state=False
                ),
            },
        }
        one_day = 60 * 60 * 24
        await cache.aset("coverage_data_op", coverage_data_op, one_day)

    return TemplateResponse(
        request, "help/coverage_opinions.html", coverage_data_op
    )

async def coverage_recap(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "help/coverage_recap.html",
        {"private": False},
    )


async def feeds(request: HttpRequest) -> HttpResponse:
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


async def podcasts(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "podcasts.html",
        {
            "oral_argument_courts": Court.objects.filter(
                in_use=True, has_oral_argument_scraper=True
            ),
            "count": await Audio.objects.all().acount(),
            "private": False,
        },
    )


async def contribute(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(request, "contribute.html", {"private": False})


async def contact(
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

            default_from = settings.DEFAULT_FROM_EMAIL
            message = EmailMessage(
                subject="[CourtListener] Contact: "
                "{phone_number}".format(**cd),
                body="Subject: {phone_number}\n"
                "From: {name} ({email})\n\n\n"
                "{message}\n\n"
                "Browser: {browser}".format(
                    browser=request.META.get("HTTP_USER_AGENT", "Unknown"),
                    **cd,
                ),
                to=["info@free.law"],
                reply_to=[cd.get("email", default_from) or default_from],
            )
            await sync_to_async(message.send)()
            return HttpResponseRedirect(reverse("contact_thanks"))
    else:
        # the form is loading for the first time
        user = await request.auser()  # type: ignore[attr-defined]
        if isinstance(user, User):
            initial["email"] = user.email
            initial["name"] = user.get_full_name()
            form = ContactForm(initial=initial)
        else:
            # for anonymous users, who lack full_names, and emails
            form = ContactForm(initial=initial)

    template_data.update({"form": form, "private": False})
    return TemplateResponse(request, template_path, template_data)


async def contact_thanks(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(request, "contact_thanks.html", {"private": True})


async def advanced_search(request: HttpRequest) -> HttpResponse:
    types = ["opinions", "parentheticals", "recap_archive", "oral_arguments"]
    json_template = loader.get_template("includes/available_fields.json")
    json_content = json_template.render()
    data = json.loads(json_content)
    return TemplateResponse(
        request,
        "help/advanced_search.html",
        {"private": False, "data": data, "types": types},
    )


async def old_terms(request: HttpRequest, v: str) -> HttpResponse:
    return TemplateResponse(
        request,
        f"terms/{v}.html",
        {
            "title": "Archived Terms of Service and Policies, v%s – "
            "CourtListener.com" % v,
            "private": True,
        },
    )


async def latest_terms(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "terms/latest.html",
        {
            "title": "Terms of Service and Policies – CourtListener.com",
            "private": False,
        },
    )


async def validate_for_wot(request: HttpRequest) -> HttpResponse:
    return HttpResponse("bcb982d1e23b7091d5cf4e46826c8fc0")


async def ratelimited(
    request: HttpRequest, exception: Exception
) -> HttpResponse:
    return TemplateResponse(
        request,
        "429.html",
        {"private": True},
        status=HTTPStatus.TOO_MANY_REQUESTS,
    )
