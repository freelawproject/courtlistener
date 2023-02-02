from admin_cursor_paginator import CursorPaginatorAdmin
from django.conf import settings
from django.contrib import admin
from django.utils.safestring import mark_safe

from cl.disclosures.tasks import make_financial_disclosure_thumbnail_from_pdf

from ..lib.admin import NotesInline
from ..lib.models import THUMBNAIL_STATUSES
from .models import (
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


@admin.register(FinancialDisclosure)
class FinancialDisclosureAdmin(admin.ModelAdmin):
    list_display = ("__str__", "get_name", "year", "filepath")

    def get_name(self, obj):
        return obj.person.name_full.title()

    raw_id_fields = ("person",)
    inlines = (NotesInline,)

    def save_model(self, request, obj, form, change):
        obj.save()
        if obj.thumbnail_status is THUMBNAIL_STATUSES.NEEDED:
            make_financial_disclosure_thumbnail_from_pdf.delay(obj.pk)


@admin.register(Investment)
class InvestmentAdmin(CursorPaginatorAdmin):
    raw_id_fields = ("financial_disclosure",)

    list_display = (
        "description_or_blank",
        "gross_value_code",
        "transaction_value_code",
        "transaction_date",
        "redacted",
    )
    search_fields = [
        "description",
    ]

    readonly_fields = ["page_link"]

    def description_or_blank(self, obj):
        if len(obj.description):
            return obj.description
        return "[Blank]"

    def page_link(self, obj):
        return mark_safe(
            f'<a href="https://{settings.AWS_S3_CUSTOM_DOMAIN}/'
            f"{obj.financial_disclosure.filepath}"
            f'#page={obj.page_number}">Link to PDF page</a>'
        )

    page_link.short_description = "Page link"


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    raw_id_fields = ("financial_disclosure",)

    list_display = ("position", "organization_name")


@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    raw_id_fields = ("financial_disclosure",)

    list_display = ("source", "description", "value")


@admin.register(Debt)
class DebtAdmin(admin.ModelAdmin):
    raw_id_fields = ("financial_disclosure",)

    list_display = ("creditor_name", "description", "value_code")


@admin.register(Reimbursement)
class ReimbursementAdmin(admin.ModelAdmin):
    raw_id_fields = ("financial_disclosure",)

    list_display = ("source", "location", "purpose", "items_paid_or_provided")


@admin.register(Agreement)
class AgreementAdmin(admin.ModelAdmin):
    raw_id_fields = ("financial_disclosure",)

    list_display = ("date_raw", "parties_and_terms")


@admin.register(NonInvestmentIncome)
class NonInvestmentIncomeAdmin(admin.ModelAdmin):
    raw_id_fields = ("financial_disclosure",)

    list_display = ("date_raw", "source_type", "income_amount")


@admin.register(SpouseIncome)
class SpouseIncomeAdmin(admin.ModelAdmin):
    raw_id_fields = ("financial_disclosure",)

    list_display = ("date_raw", "source_type", "redacted")
