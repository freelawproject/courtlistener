import datetime
import json
from typing import Dict, Union, Optional, List
from urllib.parse import quote

import requests
from dateutil.parser import parse, ParserError
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from requests import ReadTimeout

from cl.celery_init import app
from cl.lib.command_utils import logger
from cl.lib.crypto import sha1
from cl.lib.models import THUMBNAIL_STATUSES
from cl.scrapers.transformer_extractor_utils import (
    generate_thumbnail,
    get_page_count,
)


@app.task(bind=True, max_retries=2)
def make_financial_disclosure_thumbnail_from_pdf(self, pk: int) -> None:
    """Generate Thumbnail and save to AWS

    Attempt to generate thumbnail from PDF and save to AWS.

    :param self: The celery task
    :param pk: PK of disclosure in database
    :return: None
    """
    from cl.disclosures.models import FinancialDisclosure

    disclosure = FinancialDisclosure.objects.get(pk=pk)
    pdf_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{disclosure.filepath}"
    pdf_content = requests.get(url=pdf_url, timeout=2).content

    try:
        thumbnail_content = generate_thumbnail(pdf_content)
    except ReadTimeout as exc:
        if self.request.retries == self.max_retries:
            disclosure.thumbnail_status = THUMBNAIL_STATUSES.FAILED
            disclosure.save()
            return
        else:
            raise self.retry(exc=exc)

    if thumbnail_content is not None:
        disclosure.thumbnail_status = THUMBNAIL_STATUSES.COMPLETE
        disclosure.thumbnail.save(None, ContentFile(thumbnail_content))
    else:
        disclosure.thumbnail_status = THUMBNAIL_STATUSES.FAILED
        disclosure.save()


def check_if_in_system(sha1_hash: str) -> bool:
    """Check if pdf bytes hash sha1 in cl db.

    :param sha1_hash: Sha1 hash
    :return: Whether PDF is in db.
    """
    from cl.disclosures.models import FinancialDisclosure

    disclosures = FinancialDisclosure.objects.filter(sha1=sha1_hash)
    if disclosures.exists():
        logger.info("PDF already in system")
        return True
    return False


def extract_content(
    pdf_bytes: bytes,
    disclosure_type: str,
) -> Dict[str, Union[str, int]]:
    """Extract the content of the PDF.

    Attempt extraction using multiple methods if necessary.

    :param pdf_bytes: The byte array of the PDF
    :param disclosure_type: Type of disclosure
    :return:The extracted content
    """
    logger.info("Attempting extraction.")

    # Extraction takes between 7 seconds and 80 minutes for super
    # long Trump extraction with ~5k investments
    try:
        if disclosure_type == "jw":
            extractor_response = requests.post(
                settings.BTE_URLS["extract-disclosure-jw"]["url"],
                files={"file": ("file", pdf_bytes)},
                timeout=settings.BTE_URLS["extract-disclosure-jw"]["timeout"],
            )
        else:
            extractor_response = requests.post(
                settings.BTE_URLS["extract-disclosure"]["url"],
                files={"pdf_document": ("file", pdf_bytes)},
                timeout=settings.BTE_URLS["extract-disclosure"]["timeout"],
            )
    except ReadTimeout:
        logger.info("Timeout occurred for PDF")
        return {}

    status = extractor_response.status_code
    if status != 200 or extractor_response.json()["success"] is False:
        logger.info("Could not extract data from this document")
        return {}

    logger.info("Processing extracted data")
    return extractor_response.json()


def get_report_type(extracted_data: dict) -> int:
    """Get report type if available

    :param extracted_data: Document information
    :return: Disclosure type
    """
    from cl.disclosures.models import (
        REPORT_TYPES,
    )

    if extracted_data.get("initial"):
        return REPORT_TYPES.INITIAL
    elif extracted_data.get("nomination"):
        return REPORT_TYPES.NOMINATION
    elif extracted_data.get("annual"):
        return REPORT_TYPES.ANNUAL
    elif extracted_data.get("final"):
        return REPORT_TYPES.FINAL
    return REPORT_TYPES.UNKNOWN


class ChristmasError(Exception):
    """Error class for representing a Christmas date being found."""

    def __init__(self, message: str) -> None:
        self.message = message


def get_date(text: str, year: int) -> Optional[datetime.date]:
    """Extract date from date strings if possible

    Because we know year we can verify that the date is ... close.

    :param year: The year of the financial disclosure
    :param text: The extracted string version of the date
    :return: Date object or None
    """
    try:
        date_parsed = parse(
            text, fuzzy=True, default=datetime.datetime(year, 12, 25)
        )
        date_found = date_parsed.date()
        if date_found.month == 12 and date_found.day == 25:
            raise ChristmasError("Christmas error.")

        if int(date_found.year) == year:
            return date_found
        return None
    except (ParserError, ChristmasError):
        return None
    except TypeError:
        # Dateutil sometimes goes sideways
        return None


@transaction.atomic
def save_disclosure(extracted_data: dict, disclosure) -> None:
    """Save financial data to system.

    Wrapped in a transaction, we fail if anything fails.

    :param disclosure: Financial disclosure
    :param extracted_data: disclosure
    :return:None
    """
    from cl.disclosures.models import (
        Investment,
        Agreement,
        Debt,
        Gift,
        Reimbursement,
        NonInvestmentIncome,
        SpouseIncome,
        Position,
    )

    addendum = "Additional Information or Explanations"

    # Process and save our data into the system.
    disclosure.has_been_extracted = True
    disclosure.addendum_content_raw = extracted_data[addendum]["text"]
    disclosure.addendum_redacted = extracted_data[addendum]["is_redacted"]
    disclosure.is_amended = extracted_data.get("amended") or False
    disclosure.report_type = get_report_type(extracted_data)
    disclosure.save()

    Investment.objects.bulk_create(
        [
            Investment(
                financial_disclosure=disclosure,
                redacted=any(v["is_redacted"] for v in investment.values()),
                description=investment["A"]["text"],
                page_number=investment["A"]["page_number"],
                has_inferred_values=investment["A"]["inferred_value"],
                income_during_reporting_period_code=investment["B1"]["text"],
                income_during_reporting_period_type=investment["B2"]["text"],
                gross_value_code=investment["C1"]["text"],
                gross_value_method=investment["C2"]["text"],
                transaction_during_reporting_period=investment["D1"]["text"],
                transaction_date_raw=investment["D2"]["text"],
                transaction_date=get_date(
                    investment["D2"]["text"], disclosure.year
                ),
                transaction_value_code=investment["D3"]["text"],
                transaction_gain_code=investment["D4"]["text"],
                transaction_partner=investment["D5"]["text"],
            )
            for investment in extracted_data["sections"][
                "Investments and Trusts"
            ]["rows"]
        ]
    )

    Agreement.objects.bulk_create(
        [
            Agreement(
                financial_disclosure=disclosure,
                redacted=any(v["is_redacted"] for v in agreement.values()),
                date_raw=agreement["Date"]["text"],
                parties_and_terms=agreement["Parties and Terms"]["text"],
            )
            for agreement in extracted_data["sections"]["Agreements"]["rows"]
        ]
    )

    Debt.objects.bulk_create(
        [
            Debt(
                financial_disclosure=disclosure,
                redacted=any(v["is_redacted"] for v in debt.values()),
                creditor_name=debt["Creditor"]["text"],
                description=debt["Description"]["text"],
                value_code=debt["Value Code"]["text"],
            )
            for debt in extracted_data["sections"]["Liabilities"]["rows"]
        ]
    )

    Position.objects.bulk_create(
        [
            Position(
                financial_disclosure=disclosure,
                redacted=any(v["is_redacted"] for v in position.values()),
                position=position["Position"]["text"],
                organization_name=position["Name of Organization"]["text"],
            )
            for position in extracted_data["sections"]["Positions"]["rows"]
        ]
    )

    Gift.objects.bulk_create(
        [
            Gift(
                financial_disclosure=disclosure,
                source=gift["Source"]["text"],
                description=gift["Description"]["text"],
                value=gift["Value"]["text"],
                redacted=any(v["is_redacted"] for v in gift.values()),
            )
            for gift in extracted_data["sections"]["Gifts"]["rows"]
        ]
    )

    Reimbursement.objects.bulk_create(
        [
            Reimbursement(
                financial_disclosure=disclosure,
                redacted=any(v["is_redacted"] for v in reimbursement.values()),
                source=reimbursement["Source"]["text"],
                date_raw=reimbursement["Dates"]["text"],
                location=reimbursement["Locations"]["text"],
                purpose=reimbursement["Purpose"]["text"],
                items_paid_or_provided=reimbursement["Items Paid or Provided"][
                    "text"
                ],
            )
            for reimbursement in extracted_data["sections"]["Reimbursements"][
                "rows"
            ]
        ]
    )

    NonInvestmentIncome.objects.bulk_create(
        [
            NonInvestmentIncome(
                financial_disclosure=disclosure,
                redacted=any(
                    v["is_redacted"] for v in non_investment_income.values()
                ),
                date_raw=non_investment_income["Date"]["text"],
                source_type=non_investment_income["Source and Type"]["text"],
                income_amount=non_investment_income["Income"]["text"],
            )
            for non_investment_income in extracted_data["sections"][
                "Non-Investment Income"
            ]["rows"]
        ]
    )

    SpouseIncome.objects.bulk_create(
        [
            SpouseIncome(
                financial_disclosure=disclosure,
                redacted=any(v["is_redacted"] for v in spouse_income.values()),
                date_raw=spouse_income["Date"]["text"],
                source_type=spouse_income["Source and Type"]["text"],
            )
            for spouse_income in extracted_data["sections"][
                "Non Investment Income Spouse"
            ]["rows"]
        ]
    )


def get_aws_url(data: Dict[str, Union[str, int, list]]) -> str:
    """Get URL saved to download filepath

    :param data: File data
    :return: URL or first URL on AWS
    """
    if data["disclosure_type"] == "jw" or data["disclosure_type"] == "single":
        url = data["url"]
    else:
        url = data["urls"][0]
    return url


def get_disclosure_from_pdf_path(disclosure_url: str):
    """Convenience method to get disclosure from download filepath

    :param disclosure_url: The URL of the first link (if there are more than
    one) of the source FD tiff(s)/PDF
    :return: Financial Disclosure object
    """
    from cl.disclosures.models import FinancialDisclosure

    return FinancialDisclosure.objects.get(download_filepath=disclosure_url)


def has_been_pdfed(disclosure_url: str) -> Optional[str]:
    """Has file been PDFd from tiff and saved to AWS.

    :param disclosure_url: The URL of the first link (if there are more than
    one) of the source FD tiff(s)/PDF
    :return: Path to document or None
    """
    from cl.disclosures.models import FinancialDisclosure

    disclosures = FinancialDisclosure.objects.filter(
        download_filepath=disclosure_url
    )
    if disclosures.exists():
        return (
            f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/"
            f"{disclosures[0].filepath}"
        )


def generate_or_download_disclosure_as_pdf(
    data: Dict[str, Union[str, int, List[str]]],
    pdf_url: Optional[str],
) -> requests.Response:
    """Generate or download PDF content from images or urls.

    :param data: Data to process.
    :param pdf_url: The URL of PDF in S3
    :return: Response containing PDF
    """
    if pdf_url:
        logger.info(f"Downloading PDF: {pdf_url}")
        return requests.get(pdf_url, timeout=60 * 20)
    elif data["disclosure_type"] == "jw":
        logger.info(f"Downloading JW PDF: {quote(data['url'], safe=':/')}")
        return requests.get(data["url"], timeout=60 * 20)
    elif data["disclosure_type"] == "single":
        urls = [data["url"]]
    else:
        urls = data["urls"]
    logger.info(f"Processing url:{quote(urls[0], safe=':/')}")
    return requests.post(
        settings.BTE_URLS["images-to-pdf"]["url"],
        json=json.dumps({"urls": urls}),
        timeout=settings.BTE_URLS["images-to-pdf"]["timeout"],
    )


@app.task(
    bind=True,
    max_retries=2,
    interval_start=10,
)
def import_disclosure(self, data: Dict[str, Union[str, int, list]]) -> None:
    """Import disclosures into Courtlistener

    :param data: The disclosure information to process
    :return: None
    """

    from cl.disclosures.models import FinancialDisclosure
    from cl.people_db.models import Person

    # Generate PDF content from our three paths
    year = int(data["year"])
    person_id = data["person_id"]

    logger.info(
        f"Processing row {data['id']} for person {person_id} "
        f"in year {year}"
    )

    # Check if we've already extracted
    disclosure_url = get_aws_url(data)
    was_previously_pdfed = has_been_pdfed(disclosure_url)
    pdf_response = generate_or_download_disclosure_as_pdf(
        data, was_previously_pdfed
    )
    pdf_bytes = pdf_response.content

    if pdf_response.status_code != 200:
        logger.info("PDF generation failed.")
        return

    if was_previously_pdfed:
        disclosure = get_disclosure_from_pdf_path(disclosure_url)
    else:
        logger.info("PDF generated successfully.")

        # Sha1 hash - Check for duplicates
        sha1_hash = sha1(pdf_bytes)
        in_system = check_if_in_system(sha1_hash)
        if in_system:
            logger.info("PDF already in system.")
            return

        # Return page count - 0 indicates a failure of some kind.  Like PDF
        # Not actually present on aws.
        pg_count = get_page_count(pdf_bytes)
        if not pg_count:
            logger.info("PDF failed!")
            return

        # Save Financial Disclosure here to AWS and move onward
        disclosure = FinancialDisclosure(
            year=year,
            page_count=pg_count,
            person=Person.objects.get(id=person_id),
            sha1=sha1_hash,
            has_been_extracted=False,
            download_filepath=data.get("url")
            if data.get("url")
            else data.get("urls")[0],
        )
        # Save and upload PDF
        disclosure.filepath.save(
            f"{disclosure.person.slug}-disclosure.{year}.pdf",
            ContentFile(pdf_bytes),
        )
        logger.info(
            f"Uploaded to https://{settings.AWS_S3_CUSTOM_DOMAIN}/"
            f"{disclosure.filepath}"
        )
    # Extract content from PDF
    content = extract_content(
        pdf_bytes=pdf_bytes, disclosure_type=data["disclosure_type"]
    )
    if not content:
        logger.info("Failed extraction!")
        return

    # Save PDF content
    save_disclosure(extracted_data=content, disclosure=disclosure)
