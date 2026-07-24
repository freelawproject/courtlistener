import json
import logging
import re
from datetime import date
from http import HTTPStatus
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import (
    Case,
    Count,
    IntegerField,
    QuerySet,
    Sum,
    Value,
    When,
)
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template import loader
from django.template.response import TemplateResponse
from django.urls import reverse

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
from cl.favorites.models import Prayer
from cl.favorites.utils import get_lifetime_prayer_stats
from cl.people_db.models import Person
from cl.search.cluster_sources import ClusterSources
from cl.search.models import (
    Court,
    OpinionCluster,
    RECAPDocument,
)
from cl.search.selectors import get_available_documents_estimate_count
from cl.search.utils import get_redis_stat_sum
from cl.simple_pages.coverage_utils import fetch_data, fetch_federal_data
from cl.simple_pages.forms import ContactForm
from cl.simple_pages.tasks import create_zoho_desk_ticket
from cl.stats.constants import StatMetric

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
            "total_recap_count": await sync_to_async(
                get_available_documents_estimate_count
            )(),
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
    jurisdiction_ordering = Case(
        When(jurisdiction="F", then=Value(0)),
        When(jurisdiction="FD", then=Value(1)),
        When(jurisdiction="FB", then=Value(2)),
        default=Value(999),
        output_field=IntegerField(),
    )  # Sort apellate courts first, then district, then bankruptcy.

    no_feeds = (
        Court.federal_courts.all_pacer_courts()
        .filter(
            pacer_has_rss_feed=False,
        )
        .order_by(jurisdiction_ordering)
    )
    partial_feeds = (
        Court.federal_courts.all_pacer_courts()
        .filter(pacer_has_rss_feed=True)
        .exclude(pacer_rss_entry_types="all")
        .order_by(jurisdiction_ordering)
    )
    full_feeds = (
        Court.federal_courts.all_pacer_courts()
        .filter(pacer_has_rss_feed=True, pacer_rss_entry_types="all")
        .order_by(jurisdiction_ordering)
    )
    context = {
        "no_feeds": no_feeds,
        "partial_feeds": partial_feeds,
        "full_feeds": full_feeds,
        "private": False,
        "rt_alerts_sending_rate": int(
            settings.REAL_TIME_ALERTS_SENDING_RATE / 60
        ),
        "MAX_ATTORNEYS_TO_PERCOLATE": settings.MAX_ATTORNEYS_TO_PERCOLATE,
        # Yesterday's alert total; start=1 skips today's still-filling bucket.
        "alerts_sent_count": await sync_to_async(get_redis_stat_sum)(
            f"{StatMetric.ALERTS_SENT}.{{date}}", days=1, start=1
        ),
    }
    return TemplateResponse(request, "help/alert_help.html", context)


async def delete_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request, "help/delete_account_help.html", {"private": False}
    )


async def markdown_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request, "help/markdown_help.html", {"private": False}
    )


async def prayer_help(request: HttpRequest) -> HttpResponse:
    stats = await get_lifetime_prayer_stats(Prayer.GRANTED)

    context = {
        "daily_quota": settings.ALLOWED_PRAYER_COUNT,
        "private": False,
        "granted_stats": stats,
    }

    return TemplateResponse(request, "help/prayer_help.html", context)


async def relative_dates(request: HttpRequest) -> HttpResponse:
    context = {
        "private": False,
    }
    return TemplateResponse(request, "help/relative_dates_help.html", context)


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
            if ClusterSources.PUBLIC_RESOURCE in d["source"]:
                count_pro += d["source__count"]
            if ClusterSources.COURT_WEBSITE in d["source"]:
                count_scraper += d["source__count"]
            if ClusterSources.LAWBOX in d["source"]:
                count_lawbox += d["source__count"]

        opinion_courts = Court.objects.filter(
            in_use=True, has_opinion_scraper=True
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
            "private": False,
        }
        one_day = 60 * 60 * 24
        await cache.aset(coverage_cache_key, coverage_data, one_day)
    return coverage_data


async def coverage(request: HttpRequest) -> HttpResponse:
    coverage_data_o = await get_coverage_data_o(request)
    return TemplateResponse(request, "help/coverage.html", coverage_data_o)


async def coverage_oa(request: HttpRequest) -> HttpResponse:
    oral_argument_courts = Court.objects.filter(
        in_use=True, has_oral_argument_scraper=True
    )
    return TemplateResponse(
        request,
        "help/coverage_oa.html",
        {
            "courts_with_oral_argument_scrapers": oral_argument_courts,  # -> can be safely removed once new design is launched
            "courts_list": [
                {
                    "href": f"/?q=&court_{court.pk}=on&order_by=dateArgued+desc&type=oa",
                    "label": court,
                    "ref": "nofollow",
                }
                async for court in oral_argument_courts
            ],
            "private": False,
        },
    )


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
                    [Court.INTERNATIONAL], group_by_state=False
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


async def coverage_scotus(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "help/coverage_scotus.html",
        {"private": False},
    )


async def coverage_texas(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "help/coverage_texas.html",
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

    auser = await request.auser()  # type: ignore[attr-defined]
    if isinstance(auser, User):
        # Logged-in user
        is_authenticated = True
        user = auser
        account_email = user.email
    else:
        is_authenticated = False
        user = None
        account_email = ""

    if request.method == "POST":
        form = ContactForm(
            request.POST,
            is_authenticated=is_authenticated,
            account_email=account_email,
        )
        if form.is_valid():
            cd = form.cleaned_data
            # Uses phone_number as Subject field to defeat spam. If this field
            # begins with three digits, assume it's spam; fake success.
            if re.match(r"\d{3}", cd["phone_number"]):
                logger.info("Detected spam message. Not sending email.")
                return HttpResponseRedirect(reverse("contact_thanks"))

            logged_in_info: dict[str, Any] | None = None
            if user:
                profile = await sync_to_async(lambda: user.profile)()  # type: ignore[attr-defined]
                logged_in_info = {
                    "username": user.username,
                    "email": account_email,
                    "email_confirmed": profile.email_confirmed,
                }

            create_zoho_desk_ticket.delay(
                subject=cd["phone_number"],
                name=cd["name"],
                email=account_email if is_authenticated else cd["email"],
                description=form.render_email_body(
                    user_agent=request.headers.get("user-agent", "Unknown"),
                    logged_in_info=logged_in_info,
                ),
                request_type=form.get_zoho_request_type(),
                assignee_id=form.get_zoho_assignee_id(),
            )
            return HttpResponseRedirect(reverse("contact_thanks"))
    else:
        # the form is loading for the first time
        issue_type = request.GET.get("issue_type")
        if issue_type and issue_type.lower() in ContactForm.VALID_ISSUE_TYPES:
            initial["issue_type"] = issue_type.lower()
        if user:
            initial["name"] = user.get_full_name()
        form = ContactForm(
            initial=initial,
            is_authenticated=is_authenticated,
            account_email=account_email,
        )

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


async def citegeist_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(request, "citegeist.html", {"private": False})


async def validate_for_wot(request: HttpRequest) -> HttpResponse:
    return HttpResponse("bcb982d1e23b7091d5cf4e46826c8fc0")


async def components(request: HttpRequest) -> HttpResponse:
    # Mock data for docket entry rows demo
    class MockRECAPDoc:
        PACER_DOCUMENT = RECAPDocument.PACER_DOCUMENT
        ATTACHMENT = RECAPDocument.ATTACHMENT

        def __init__(
            self,
            *,
            document_type: int = RECAPDocument.PACER_DOCUMENT,
            document_number: str = "1",
            attachment_number: int | None = None,
            description: str = "",
            filepath_local: str = "",
            filepath_ia: str = "",
            is_available: bool = False,
            is_sealed: bool | None = None,
            is_free_on_pacer: bool | None = None,
            page_count: int | None = None,
            pacer_doc_id: str = "",
            prayer_count: int = 0,
            prayer_exists: bool = False,
            pk: int = 0,
        ):
            self.document_type = document_type
            self.document_number = document_number
            self.attachment_number = attachment_number
            self.description = description
            self.filepath_local = filepath_local
            self.filepath_ia = filepath_ia
            self.is_available = is_available
            self.is_sealed = is_sealed
            self.is_free_on_pacer = is_free_on_pacer
            self.page_count = page_count
            self.pacer_doc_id = pacer_doc_id
            self.prayer_count = prayer_count
            self.prayer_exists = prayer_exists
            self.id = pk
            self.pk = pk
            self.date_upload = None

        @property
        def pacer_url(self) -> str:
            if self.pacer_doc_id:
                return (
                    f"https://ecf.canb.uscourts.gov/doc1/{self.pacer_doc_id}"
                )
            return ""

        def get_absolute_url(self) -> str:
            return f"/docket/{self.pk}/document/"

    class MockRECAPDocManager:
        def __init__(self, docs: list[MockRECAPDoc]):
            self._docs = docs

        def all(self) -> list[MockRECAPDoc]:
            return self._docs

        def count(self) -> int:
            return len(self._docs)

    class MockDocketEntry:
        def __init__(
            self,
            *,
            entry_number: int | None,
            date_filed: date,
            description: str,
            recap_documents: list[MockRECAPDoc],
            pk: int = 0,
        ):
            self.entry_number = entry_number
            self.date_filed = date_filed
            self.datetime_filed = None
            self.description = description
            self.recap_documents = MockRECAPDocManager(recap_documents)
            self.pk = pk

    demo_entries = [
        MockDocketEntry(
            entry_number=1,
            date_filed=date(2024, 4, 21),
            description=(
                "COMPLAINT against All Defendants United States of America"
                " (Filing fee $400 receipt number 0090-4495374)"
            ),
            pk=100,
            recap_documents=[
                MockRECAPDoc(
                    document_type=RECAPDocument.PACER_DOCUMENT,
                    document_number="1",
                    description="Complaint",
                    filepath_local="/mock/complaint.pdf",
                    filepath_ia="https://archive.org/download/mock/complaint.pdf",
                    is_available=True,
                    pacer_doc_id="09876",
                    page_count=10,
                    pk=1001,
                ),
                MockRECAPDoc(
                    document_type=RECAPDocument.ATTACHMENT,
                    document_number="1",
                    attachment_number=1,
                    description="Civil Cover Sheet",
                    filepath_local="/mock/cover_sheet.pdf",
                    is_available=True,
                    pk=1002,
                ),
                MockRECAPDoc(
                    document_type=RECAPDocument.ATTACHMENT,
                    document_number="1",
                    attachment_number=2,
                    description="Summons to United States Attorney General",
                    pacer_doc_id="09877",
                    page_count=4,
                    pk=1003,
                ),
            ],
        ),
        MockDocketEntry(
            entry_number=None,
            date_filed=date(2024, 4, 21),
            description="Case Assigned to Judge Ellen S. Huvelle. (jd)",
            pk=101,
            recap_documents=[],
        ),
    ]

    # Mock page object for component library demos
    class MockPaginator:
        num_pages = 10

    class MockPageObj:
        number = 3
        has_previous = True
        has_next = True
        has_other_pages = True
        paginator = MockPaginator()

        def previous_page_number(self) -> int:
            return self.number - 1

        def next_page_number(self) -> int:
            return self.number + 1

    class MockFieldValue:
        value = None

    class MockDocketFilterForm:
        errors: dict[str, list[str]] = {}
        filed_after = MockFieldValue()
        filed_before = MockFieldValue()
        entry_gte = MockFieldValue()
        entry_lte = MockFieldValue()

    class MockDocket:
        pk = 12345

    return TemplateResponse(
        request,
        "components.html",
        {
            "private": True,
            "demo_docket_entries": demo_entries,
            "demo_page_obj": MockPageObj(),
            "demo_docket": MockDocket(),
            "demo_filter_form": MockDocketFilterForm(),
        },
    )


async def ratelimited(
    request: HttpRequest, exception: Exception
) -> HttpResponse:
    return TemplateResponse(
        request,
        "429.html",
        {"private": True},
        status=HTTPStatus.TOO_MANY_REQUESTS,
    )
