from typing import Dict, Optional, Union

import pghistory
from django.db import models
from django.urls import reverse

from cl.lib.models import THUMBNAIL_STATUSES, AbstractDateTimeModel
from cl.lib.pghistory import AfterUpdateOrDeleteSnapshot
from cl.lib.storage import IncrementingAWSMediaStorage
from cl.people_db.models import Person


class REPORT_TYPES(object):
    """If extracted, we identify what type of disclosure was reported."""

    UNKNOWN = -1
    NOMINATION = 0
    INITIAL = 1
    ANNUAL = 2
    FINAL = 3
    NAMES = (
        (UNKNOWN, "Unknown Report"),
        (NOMINATION, "Nomination Report"),
        (INITIAL, "Initial Report"),
        (ANNUAL, "Annual Report"),
        (FINAL, "Final Report"),
    )


class CODES(object):
    # FORM CODES - these are used in multiple fields in different sections
    # of the disclosures.  For example liabilities/debts uses Gross Value
    # As well as investments.
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
    Q = "Q"
    R = "R"
    S = "S"
    T = "T"
    U = "U"
    V = "V"
    W = "W"

    # Failed Extraction
    X = "-1"

    VALUATION_METHODS = (
        (Q, "Appraisal"),
        (R, "Cost (Real Estate Only)"),
        (S, "Assessment"),
        (T, "Cash Market"),
        (U, "Book Value"),
        (V, "Other"),
        (W, "Estimated"),
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

    VALUES: Dict[str, Dict[str, Optional[int]]] = {
        A: {"min": 1, "max": 1_000},
        B: {"min": 1_001, "max": 2_500},
        C: {"min": 2_501, "max": 5_000},
        D: {"min": 5_001, "max": 15_000},
        E: {"min": 15_001, "max": 50_000},
        F: {"min": 50_001, "max": 100_000},
        G: {"min": 100_001, "max": 1_000_000},
        H1: {"min": 1_000_001, "max": 5_000_000},
        H2: {"min": 5_000_001, "max": None},
        J: {"min": 1, "max": 15_000},
        K: {"min": 15_001, "max": 50_000},
        L: {"min": 50_001, "max": 100_000},
        M: {"min": 100_001, "max": 250_000},
        N: {"min": 250_001, "max": 500_000},
        O: {"min": 500_001, "max": 1_000_000},
        P1: {"min": 1_000_001, "max": 5_000_000},
        P2: {"min": 5_000_001, "max": 25_000_000},
        P3: {"min": 25_000_001, "max": 50_000_000},
        P4: {"min": 50_000_001, "max": None},
    }


S3_TEMPLATE = (
    "us/federal/judicial/financial-disclosures/"
    "{person_id}/{slug}-disclosure.{year}"
)


def thumbnail_path(
    instance: "FinancialDisclosure",
    filename: str = None,
) -> str:
    """Generate thumbnail location for disclosures

    :param instance: The disclosure
    :param filename: An empty value - not sure why its needed
    :return: Location to save thumbnail
    """
    return (
        S3_TEMPLATE.format(
            person_id=instance.person.id,
            slug=instance.person.slug,
            year=instance.year,
        )
        + "-thumbnail.png"
    )


def pdf_path(
    instance: "FinancialDisclosure",
    filename: str = None,
) -> str:
    """Generate a path for the FD PDF

    :param instance: The disclosure object
    :param filename: The name of the file
    :return: Location to save the PDF
    """
    return (
        S3_TEMPLATE.format(
            person_id=instance.person.id,
            slug=instance.person.slug,
            year=instance.year,
        )
        + ".pdf"
    )


disclosure_permissions = (
    ("has_disclosure_api_access", "Can work with Disclosure API"),
)


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class FinancialDisclosure(AbstractDateTimeModel):
    """A simple table to hold references to financial disclosure forms"""

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
    download_filepath = models.TextField(
        help_text="The path to the original file collected on aws. If "
        "split tiff, return url for page one of the disclosures",
    )
    filepath = models.FileField(
        help_text="The filepath to the disclosure normalized to a PDF.",
        upload_to=pdf_path,
        storage=IncrementingAWSMediaStorage(),
        max_length=300,
        db_index=True,
    )
    thumbnail = models.FileField(
        help_text="A thumbnail of the first page of the disclosure form.",
        upload_to=thumbnail_path,
        storage=IncrementingAWSMediaStorage(),
        max_length=300,
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
        help_text="SHA1 hash of the generated PDF",
        max_length=40,
        db_index=True,
        blank=True,
        unique=True,
    )
    report_type = models.SmallIntegerField(
        help_text="Financial Disclosure report type",
        choices=REPORT_TYPES.NAMES,
        default=REPORT_TYPES.UNKNOWN,
    )
    is_amended = models.BooleanField(
        help_text="Is disclosure amended?",
        default=False,
        null=True,
    )
    addendum_content_raw = models.TextField(
        help_text="Raw content of addendum with whitespace preserved.",
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

    def __str__(self) -> str:
        return f"{self.pk}, person: {self.person_id}, year: {self.year}"

    def get_absolute_url(self) -> str:
        return reverse(
            "financial_disclosures_viewer",
            args=(self.person.pk, self.pk, self.person.slug),
        )

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
        investments = self.investments.exclude(
            **{field_name: CODES.X}
        ).exclude(**{field_name: ""})

        min_value, max_value = 0, 0
        for investment in investments:
            min_value += CODES.VALUES[getattr(investment, field_name)]["min"]
            max_value += CODES.VALUES[getattr(investment, field_name)]["max"]
        return {
            "min": min_value,
            "max": max_value,
            "miss_count": self.investments.filter(
                **{field_name: CODES.X}
            ).count(),
        }

    def save(self, *args, **kwargs):
        super(FinancialDisclosure, self).save(*args, **kwargs)
        if self.thumbnail_status == THUMBNAIL_STATUSES.NEEDED:
            from cl.disclosures.tasks import (
                make_financial_disclosure_thumbnail_from_pdf,
            )

            make_financial_disclosure_thumbnail_from_pdf.delay(self.pk)

    class Meta:
        permissions = disclosure_permissions


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class Investment(AbstractDateTimeModel):
    """Financial Disclosure Investments Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated with this investment.",
        related_name="investments",
        on_delete=models.CASCADE,
    )
    page_number = models.IntegerField(
        help_text="The page number the investment is listed on.  This is used"
        " to generate links directly to the PDF page.",
    )
    description = models.TextField(
        help_text="Name of investment (ex. APPL common stock).", blank=True
    )
    redacted = models.BooleanField(
        help_text="Does the investment row contains redaction(s)?",
        default=False,
    )
    income_during_reporting_period_code = models.CharField(
        help_text="Increase in investment value - as a form code",
        choices=CODES.INCOME_GAIN,
        max_length=5,
        blank=True,
    )
    income_during_reporting_period_type = models.TextField(
        help_text="Type of investment (ex. Rent, Dividend). Typically "
        "standardized but not universally.",
        blank=True,
    )
    gross_value_code = models.CharField(
        help_text="Investment total value code at end "
        "of reporting period as code (ex. J (1-15,000)).",
        choices=CODES.GROSS_VALUE,
        blank=True,
        max_length=5,
    )
    gross_value_method = models.CharField(
        help_text="Investment valuation method code (ex. Q = Appraisal)",
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
        help_text="Transaction value amount, as form code (ex. J (1-15,000)).",
        choices=CODES.GROSS_VALUE,
        blank=True,
        max_length=5,
    )
    transaction_gain_code = models.CharField(
        help_text="Gain from investment transaction if any (ex. A (1-1000)).",
        choices=CODES.INCOME_GAIN,
        max_length=5,
        blank=True,
    )
    transaction_partner = models.TextField(
        help_text="Identity of the transaction partner", blank=True
    )
    has_inferred_values = models.BooleanField(
        help_text="If the investment name was inferred during extraction. "
        "This is common because transactions usually list the first "
        "purchase of a stock and leave the name value blank for "
        "subsequent purchases or sales.",
        default=False,
    )

    class Meta:
        permissions = disclosure_permissions


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class Position(AbstractDateTimeModel):
    """Financial Disclosure Position Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated "
        "with this financial position.",
        related_name="positions",
        on_delete=models.CASCADE,
    )
    position = models.TextField(
        help_text="Position title (ex. Trustee).",
        blank=True,
    )
    organization_name = models.TextField(
        help_text="Name of organization or entity (ex. Trust #1).",
        blank=True,
    )
    redacted = models.BooleanField(
        help_text="Does the position row contain redaction(s)?",
        default=False,
    )

    class Meta:
        permissions = disclosure_permissions


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class Agreement(AbstractDateTimeModel):
    """Financial Disclosure Agreements Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated with this agreement.",
        related_name="agreements",
        on_delete=models.CASCADE,
    )
    date_raw = models.TextField(
        help_text="Date of judicial agreement.",
        blank=True,
    )
    parties_and_terms = models.TextField(
        help_text="Parties and terms of agreement "
        "(ex. Board Member NY Ballet)",
        blank=True,
    )
    redacted = models.BooleanField(
        help_text="Does the agreement row contain redaction(s)?",
        default=False,
    )

    class Meta:
        permissions = disclosure_permissions


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class NonInvestmentIncome(AbstractDateTimeModel):
    """Financial Disclosure Non Investment Income Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated "
        "with this non-investment income.",
        related_name="non_investment_incomes",
        on_delete=models.CASCADE,
    )
    date_raw = models.TextField(
        help_text="Date of non-investment income (ex. 2011).",
        blank=True,
    )
    source_type = models.TextField(
        help_text="Source and type of non-investment income for the judge "
        "(ex. Teaching a class at U. Miami).",
        blank=True,
    )
    income_amount = models.TextField(
        help_text="Amount earned by judge, often a number, but sometimes with "
        "explanatory text (e.g. 'Income at firm: $xyz').",
        blank=True,
    )
    redacted = models.BooleanField(
        help_text="Does the non-investment income row contain redaction(s)?",
        default=False,
    )

    class Meta:
        permissions = disclosure_permissions


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class SpouseIncome(AbstractDateTimeModel):
    """Financial Disclosure Judge Spouse Income Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated "
        "with this spouse income.",
        related_name="spouse_incomes",
        on_delete=models.CASCADE,
    )
    source_type = models.TextField(
        help_text="Source and type of income of judicial spouse "
        "(ex. Salary from Bank job).",
        blank=True,
    )
    date_raw = models.TextField(
        help_text="Date of spousal income (ex. 2011).",
        blank=True,
    )
    redacted = models.BooleanField(
        help_text="Does the spousal-income row contain redaction(s)?",
        default=False,
    )

    class Meta:
        permissions = disclosure_permissions


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class Reimbursement(AbstractDateTimeModel):
    """Reimbursements listed in judicial disclosure"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated "
        "with this reimbursement.",
        related_name="reimbursements",
        on_delete=models.CASCADE,
    )
    source = models.TextField(
        help_text="Source of the reimbursement (ex. FSU Law School).",
        blank=True,
    )
    date_raw = models.TextField(
        help_text="Dates as a text string for the date of reimbursements. "
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
        help_text="Does the reimbursement contain redaction(s)?",
        default=False,
    )

    class Meta:
        permissions = disclosure_permissions


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class Gift(AbstractDateTimeModel):
    """Financial Disclosure Gifts Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated with this gift.",
        related_name="gifts",
        on_delete=models.CASCADE,
    )
    source = models.TextField(
        help_text="Source of the judicial gift. (ex. Alta Ski Area).",
        blank=True,
    )
    description = models.TextField(
        help_text="Description of the gift (ex. Season Pass).",
        blank=True,
    )
    value = models.TextField(
        help_text="Value of the judicial gift, (ex. $1,199.00)",
        blank=True,
    )
    redacted = models.BooleanField(
        help_text="Does the gift row contain redaction(s)?",
        default=False,
    )

    class Meta:
        permissions = disclosure_permissions


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class Debt(AbstractDateTimeModel):
    """Financial Disclosure Judicial Debts/Liabilities Table"""

    financial_disclosure = models.ForeignKey(
        FinancialDisclosure,
        help_text="The financial disclosure associated with this debt.",
        related_name="debts",
        on_delete=models.CASCADE,
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
        help_text="Does the debt row contain redaction(s)?",
        default=False,
    )

    class Meta:
        permissions = disclosure_permissions
