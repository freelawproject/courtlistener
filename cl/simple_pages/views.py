import logging
import re
from datetime import date
from http import HTTPStatus
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

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
from cl.search.models import RECAPDocument
from cl.simple_pages.forms import ContactForm
from cl.simple_pages.tasks import create_zoho_desk_ticket

logger = logging.getLogger(__name__)


async def about(request: HttpRequest) -> HttpResponse:
    """Loads the about page"""
    return TemplateResponse(request, "about.html", {"private": False})


async def help_home(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(request, "help/index.html", {"private": False})


async def broken_email_help(request: HttpRequest) -> HttpResponse:
    return TemplateResponse(
        request,
        "help/broken_email_help.html",
        {"private": True},
    )


async def get_coverage_data_fds(bust_cache: bool = False) -> dict[str, int]:
    """Get stats on the disclosure data

    Attempt the cache if possible.

    :param bust_cache: If True, skip the cache and recompute fresh counts,
        e.g. when a caller's own cache was just busted and needs this data
        to actually be current rather than up to a week stale.
    :return: A dict mapping item types to their counts.
    """
    coverage_key = "coverage-data.fd3"
    coverage_data = None if bust_cache else await cache.aget(coverage_key)
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
