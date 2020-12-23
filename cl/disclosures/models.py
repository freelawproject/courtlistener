import re
from typing import Dict, Union

from django.db import models

from cl.lib.model_helpers import make_pdf_path, make_pdf_thumb_path
from cl.lib.models import THUMBNAIL_STATUSES
from cl.lib.storage import AWSMediaStorage
from cl.people_db.models import Person
from cl.disclosures.tasks import (
    make_financial_disclosure_thumbnail_from_pdf,
)


class REPORT_TYPES(object):

    UNKNOWN = -1
    NOMINATION = 0
    INITIAL = 1
    ANNUAL = 2
    FINAL = 3
    NAMES = (
        (UNKNOWN, "Unknown"),
        (NOMINATION, "Nomination"),
        (INITIAL, "Initial"),
        (ANNUAL, "Annual"),
        (FINAL, "Final"),
    )


class CODES(object):

    # FORM CODES
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"
    H1 = "H1"
    H2 = "H2"
    J = "J"
    K = "K"
    L = "L"
    M = "M"
    N = "N"
    O = "O"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"  # $50,000,001 and up

    # Value method calculations
    Q = "Appraisal"
    R = "Cost (Real Estate Only)"
    S = "Assessment"
    T = "Cash Market"
    U = "Book Value"
    V = "Other"

    # Failed Extraction
    X = "•"

    VALUATION_METHODS = (
        (Q, "Appraisal"),
        (R, "Cost (Real Estate Only)"),
        (S, "Assessment"),
        (T, "Cash Market"),
        (U, "Book Value"),
        (V, "Other"),
        (X, "Failed Extraction"),
    )

    # INCOME GAIN CODES
    INCOME_GAIN = (
        (A, "1 - 1,000"),
        (B, "1,001 - 2,500"),
        (C, "2,501 - 5,000"),
        (D, "5,001 - 15,000"),
        (E, "15,001 - 50,000"),
        (F, "50,001 - 100,000"),
        (G, "100,001 - 1,000,000"),
        (H1, "1,000,001 - 5,000,000"),
        (H2, "5,000,001 +"),
        (X, "Failed Extraction"),
    )

    GROSS_VALUE = (
        (J, "1 - 15,000"),
        (K, "15,001 - 50,000"),
        (L, "50,001 - 100,000"),
        (M, "100,001 - 250,000"),
        (N, "250,001 - 500,000"),
        (O, "500,001 - 1,000,000"),
        (P1, "1,000,001 - 5,000,000"),
        (P2, "5,000,001 - 25,000,000"),
        (P3, "25,000,001 - 50,000,000"),
        (P4, "50,000,001 - "),
        (X, "Failed Extraction"),
    )


class FinancialDisclosure(models.Model):
    """A simple table to hold references to financial disclosure forms"""

    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    person = models.ForeignKey(
        Person,
        help_text="The person that the document is associated with.",
        related_name="financial_disclosures",
        on_delete=models.CASCADE,
    )
    year = models.SmallIntegerField(
        help_text="The year that the disclosure corresponds with",
        db_index=True,
    )
    filepath = models.FileField(
        help_text="The disclosure report itself",
        upload_to=make_pdf_path,
        storage=AWSMediaStorage(),
        db_index=True,
    )
    thumbnail = models.FileField(
        help_text="A thumbnail of the first page of the disclosure form",
        upload_to=make_pdf_thumb_path,
        storage=AWSMediaStorage(),
        null=True,
        blank=True,
    )
    thumbnail_status = models.SmallIntegerField(
        help_text="The status of the thumbnail generation",
        choices=THUMBNAIL_STATUSES.NAMES,
        default=THUMBNAIL_STATUSES.NEEDED,
    )
    page_count = models.SmallIntegerField(
        help_text="The number of pages in the disclosure report",
    )
    sha1 = models.CharField(
        help_text="PDF hash, used to identify duplicate PDFs",
        max_length=40,
        db_index=True,
        blank=True,
    )
    report_type = models.SmallIntegerField(
        help_text="Financial Disclosure report type",
        choices=REPORT_TYPES.NAMES,
        default=REPORT_TYPES.UNKNOWN,
    )
    is_amended = models.BooleanField(
        help_text="Is disclosure amended?",
        default=False,
    )
    addendum_content_raw = models.TextField(
        help_text="Raw content of addendum.",
        blank=True,
    )
    addendum_redacted = models.BooleanField(
        help_text="Is the addendum partially or completely redacted?",
        default=False,
    )
    has_been_extracted = models.BooleanField(
        help_text="Have we successfully extracted the data from PDF?",
        default=False,
    )

    class Meta:
        ordering = ("-year",)

    def calculate_wealth(self, field_name: str) -> Dict[str, Union[str, int]]:
        """Calculate gross value of all investments in disclosure

        We can calculate the total investment for four fields

        ** gross_value_code - Gross Value total for the investments
        ** income_during_reporting_period_code - Gross Income
        ** transaction_gain_code  - Total Income gain
        ** transaction_value_code - Total Transaction values

        :param field_name: The field to process for the disclosure
        :return: Total value of investments for supplied field.
        """
        wealth = {}
        min_max = (0, 0)
        investments = (
            Investment.objects.filter(financial_disclosure=self)
            .exclude(**{field_name: "•"})
            .exclude(**{field_name: ""})
        )
        wealth["miss_count"] = (
            Investment.objects.filter(financial_disclosure=self)
            .filter(**{field_name: "•"})
            .count()
        )
        for investment in investments:
            get_display = getattr(investment, f"get_{field_name}_display")()
            if get_display is None:
                wealth["msg"] = "Field not recognized"
                return wealth
            new_min_max = re.findall(r"([0-9,]{1,12})", get_display)
            new_min_max = [int(x.replace(",", "")) for x in new_min_max]
            min_max = [i + j for i, j in zip(min_max, new_min_max)]
        wealth["min"], wealth["max"] = min_max
        return wealth

    def save(self, *args, **kwargs):
        super(FinancialDisclosure, self).save(*args, **kwargs)
        if self.thumbnail_status is THUMBNAIL_STATUSES.NEEDED:
            make_financial_disclosure_thumbnail_from_pdf.delay(self.pk)


class Investment(models.Model):
    """ Financial Disclosure Investments Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated with this investment.",
        related_name="investments",
        on_delete=models.CASCADE,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    page_number = models.IntegerField(
        help_text="The page the investment is listed on",
    )
    description = models.TextField(help_text="Name of investment", blank=True)
    redacted = models.BooleanField(
        help_text="Whether investment contains redactions.",
        default=False,
    )
    income_during_reporting_period_code = models.CharField(
        help_text="Increase in investment value - as a form code",
        choices=CODES.INCOME_GAIN,
        max_length=5,
        blank=True,
    )
    income_during_reporting_period_type = models.TextField(
        help_text="Type of investment ex. Rent, Dividend.  Typically "
        "standardized but not universally",
        blank=True,
    )
    gross_value_code = models.CharField(
        help_text="Investment total value code at end "
        "of reporting period as code",
        choices=CODES.GROSS_VALUE,
        blank=True,
        max_length=5,
    )
    gross_value_method = models.CharField(
        help_text="Investment valuation method code",
        choices=CODES.VALUATION_METHODS,
        blank=True,
        max_length=5,
    )
    # Transactions indicate if the investment was bought sold etc.
    # during the reporting period
    transaction_during_reporting_period = models.TextField(
        help_text="Transaction of investment during "
        "reporting period (ex. Buy, Sold)",
        blank=True,
    )
    transaction_date_raw = models.CharField(
        help_text="Date of the transaction, if any (D2)",
        blank=True,
        max_length=40,
    )
    transaction_date = models.DateField(
        help_text="Datetime value for if any (D2)", blank=True, null=True
    )
    transaction_value_code = models.CharField(
        help_text="Transaction value amount, as form code",
        choices=CODES.GROSS_VALUE,
        blank=True,
        max_length=5,
    )
    transaction_gain_code = models.CharField(
        help_text="Gain from investment transaction if any",
        choices=CODES.INCOME_GAIN,
        max_length=5,
        blank=True,
    )
    transaction_partner = models.TextField(
        help_text="Identity of the transaction partner", blank=True
    )
    has_inferred_values = models.BooleanField(
        help_text="The investment name was inferred during extraction",
        default=False,
    )


class Position(models.Model):
    """ Financial Disclosure Position Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated "
        "with this financial position.",
        related_name="financial_positions",
        on_delete=models.CASCADE,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    position = models.TextField(
        help_text="Position title.",
        blank=True,
    )
    organization_name = models.TextField(
        help_text="Name of organization or entity.",
        blank=True,
    )
    redacted = models.BooleanField(
        help_text="Financial Disclosure filing option",
        default=False,
    )


class Agreement(models.Model):
    """ Financial Disclosure Agreements Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated with this agreement.",
        related_name="agreements",
        on_delete=models.CASCADE,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    date = models.TextField(
        help_text="Date of judicial agreement.",
        blank=True,
    )
    parties_and_terms = models.TextField(
        help_text="Parties and terms of agreement.",
        blank=True,
    )
    redacted = models.BooleanField(
        help_text="Is the agreement redacted?",
        default=False,
    )


class NonInvestmentIncome(models.Model):
    """Financial Disclosure Non Investment Income Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated "
        "with this non-investment income.",
        related_name="non_investment_incomes",
        on_delete=models.CASCADE,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    date = models.TextField(
        help_text="Date of non-investment income (ex. 2011).",
        blank=True,
    )
    source_type = models.TextField(
        help_text="Source and type of non-investment income for the judge "
        "(ex. Teaching a class at U. Miami).",
        blank=True,
    )
    income_amount = models.TextField(
        help_text="Amount earned by judge.",
        blank=True,
    )
    redacted = models.BooleanField(
        help_text="Is non-investment income redacted?",
        default=False,
    )


class SpouseIncome(models.Model):
    """ Financial Disclosure Judge Spouse Income Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated "
        "with this spouse income.",
        related_name="spouse_incomes",
        on_delete=models.CASCADE,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    source_type = models.TextField(
        help_text="Source and Type of income of judicial spouse",
        blank=True,
    )
    date = models.TextField(
        help_text="Date of spousal income (ex. 2011).",
        blank=True,
    )
    redacted = models.TextField(
        help_text="Is judicial spousal income redacted?",
        default=False,
    )


class Reimbursement(models.Model):
    """Reimbursements listed in judicial disclosure"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated "
        "with this reimbursement.",
        related_name="reimbursements",
        on_delete=models.CASCADE,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    source = models.TextField(
        help_text="Source of the reimbursement (ex. FSU Law School).",
        blank=True,
    )
    dates = models.TextField(
        help_text="Dates as a text string for the date of reimbursements."
        "This is often conference dates (ex. June 2-6, 2011).",
        blank=True,
    )
    location = models.TextField(
        help_text="Location of the reimbursement "
        "(ex. Harvard Law School, Cambridge, MA).",
        blank=True,
    )
    purpose = models.TextField(
        help_text="Purpose of the reimbursement (ex. Baseball announcer).",
        blank=True,
    )
    items_paid_or_provided = models.TextField(
        help_text="Items reimbursed (ex. Room, Airfare).",
        blank=True,
    )
    redacted = models.BooleanField(
        help_text="Does the reimbursement contain redactions?",
        default=False,
    )


class Gift(models.Model):
    """ Financial Disclosure Gifts Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated with this gift.",
        related_name="gifts",
        on_delete=models.CASCADE,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )

    source = models.TextField(
        help_text="Source of the judicial gift.",
        blank=True,
    )
    description = models.TextField(
        help_text="Description of the gift.",
        blank=True,
    )
    value_code = models.TextField(
        help_text="Value of the judicial gift, as Value Code.",
        choices=CODES.GROSS_VALUE,
        blank=True,
    )
    redacted = models.BooleanField(
        help_text="Is the gift redacted?",
        default=False,
    )


class Debt(models.Model):
    """ Financial Disclosure Judicial Debts/Liabilities Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated with this debt.",
        related_name="debts",
        on_delete=models.CASCADE,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    creditor_name = models.TextField(
        help_text="Liability/Debt creditor", blank=True
    )
    description = models.TextField(
        help_text="Description of the debt", blank=True
    )
    value_code = models.CharField(
        help_text="Form code for the value of the judicial debt.",
        choices=CODES.GROSS_VALUE,
        blank=True,
        max_length=5,
    )
    redacted = models.BooleanField(
        help_text="Is the debt redacted?",
        default=False,
    )
