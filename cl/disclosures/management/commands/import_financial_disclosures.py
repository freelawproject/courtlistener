import datetime
import json
from typing import Dict, Union, Optional, List
from urllib.parse import quote

import requests
from dateutil.parser import parse, ParserError
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.crypto import sha1
from cl.disclosures.models import (
    FinancialDisclosure,
    Investment,
    Agreement,
    Debt,
    Gift,
    Reimbursement,
    NonInvestmentIncome,
    SpouseIncome,
    Position,
    REPORT_TYPES,
)
from cl.people_db.models import Person
from cl.scrapers.transformer_extractor_utils import get_page_count


def check_if_in_system(sha1_hash: str) -> bool:
    """Check if pdf bytes hash sha1 in cl db.

    :param sha1_hash: Sha1 hash
    :return: Whether PDF is in db.
    """
    disclosures = FinancialDisclosure.objects.filter(sha1=sha1_hash)
    if disclosures.exists():
        logger.info("PDF already in system")
        return True
    return False


def extract_content(pdf_bytes: bytes) -> Dict[str, Union[str, int]]:
    """Extract the content of the PDF.

    Attempt extraction using multiple methods if necessary.

    :param pdf_bytes: The byte array of the PDF
    :return:The extracted content
    """
    logger.info("Attempting extraction.")

    # Extraction takes between 7 seconds and 80 minutes for super
    # long Trump extraction with ~5k investments
    extractor_response = requests.post(
        settings.BTE_URLS["extract-disclosure"],
        files={"pdf_document": ("file", pdf_bytes)},
        timeout=60 * 60 * 2,
    )
    status = extractor_response.status_code
    success = extractor_response.json()["success"]
    if status != 200 or success is False:
        # Try less accurate and slower judicial watch endpoint.
        logger.info("Attempting second extraction")
        extractor_response = requests.post(
            settings.BTE_URLS["extract-disclosure-jw"],
            files={"file": ("file", pdf_bytes)},
            timeout=60 * 60,
        )
        status = extractor_response.status_code
        success = extractor_response.json()["success"]

        if status != 200 or success is False:
            logger.info("Could not extract data from this document")
            return {}

    logger.info("Processing extracted data")
    return extractor_response.json()


def get_report_type(extracted_data: dict) -> int:
    """Get report type if available

    :param extracted_data: Document information
    :return: Disclosure type
    """
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
    except (ParserError, ChristmasError, TypeError):
        return None


@transaction.atomic
def save_disclosure(
    extracted_data: dict, disclosure: FinancialDisclosure
) -> None:
    """Save financial data to system.

    Wrapped in a transaction, we fail if anything fails.

    :param disclosure: Financial disclosure
    :param extracted_data: disclosure
    :return:None
    """
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


def has_been_extracted(data: Dict[str, Union[str, int, list]]) -> bool:
    """Has PDF been extracted

    Method added to skip tiff to pdf conversion if
    document has already been converted and saved but
    not yet extracted.

    :param data: File data
    :return: Whether document has been extracted
    """
    if data["disclosure_type"] == "jw" or data["disclosure_type"] == "single":
        url = data["url"]
    else:
        url = data["urls"][0]

    return FinancialDisclosure.objects.filter(
        download_filepath=url, has_been_extracted=True
    ).exists()


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


def get_disclosure_from_pdf_path(disclosure_url: str) -> FinancialDisclosure:
    """Convenience method to get disclosure from download filepath

    :param disclosure_url: The URL of the first link (if there are more than
    one) of the source FD tiff(s)/PDF
    :return: Financial Disclosure object
    """
    return FinancialDisclosure.objects.get(download_filepath=disclosure_url)


def has_been_pdfed(disclosure_url: str) -> Optional[str]:
    """Has file been PDFd from tiff and saved to AWS.

    :param disclosure_url: The URL of the first link (if there are more than
    one) of the source FD tiff(s)/PDF
    :return: Path to document or None
    """

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
        settings.BTE_URLS["images-to-pdf"],
        json=json.dumps({"urls": urls}),
        timeout=10 * 60,
    )


def import_financial_disclosures(
    filepath: str,
    skip_until: Optional[str],
):
    """Import financial documents into courtlistener

    :param filepath: Path to file data to import.
    :param skip_until: ID if any to skip until.
    :return:None
    """
    with open(filepath) as f:
        disclosures = json.load(f)

    for data in disclosures:
        if data["id"] < skip_until:
            continue
        # Check download_filepath to see if it has been processed before.
        if has_been_extracted(data):
            logger.info("Document already extracted and saved.")
            continue
        # Generate PDF content from our three paths
        year = int(data["year"])
        person_id = data["person_id"]
        logger.info(f"Processing id:{person_id} " f"year:{year}")

        # Check if we've already extracted
        disclosure_url = get_aws_url(data)
        was_previously_pdfed = has_been_pdfed(disclosure_url)
        pdf_response = generate_or_download_disclosure_as_pdf(
            data, was_previously_pdfed
        )
        pdf_bytes = pdf_response.content

        if pdf_response.status_code != 200:
            logger.info("PDF generation failed.")
            continue

        if was_previously_pdfed:
            disclosure = get_disclosure_from_pdf_path(disclosure_url)
        else:
            logger.info("PDF generated successfully.")

            # Sha1 hash - Check for duplicates
            sha1_hash = sha1(pdf_bytes)
            in_system = check_if_in_system(sha1_hash)
            if in_system:
                logger.info("PDF already in system.")
                continue

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
                save=False,
            )
            logger.info(
                f"Uploaded to https://{settings.AWS_S3_CUSTOM_DOMAIN}/"
                f"{disclosure.filepath}"
            )
        # Extract content from PDF
        content = extract_content(pdf_bytes=pdf_bytes)
        if not content:
            logger.info("Failed extraction!")
            return

        # Save PDF content
        save_disclosure(extracted_data=content, disclosure=disclosure)


class Command(VerboseCommand):
    help = "Add financial disclosures to CL database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--filepath",
            required=True,
            help="Filepath to json identify documents to process.",
        )

        parser.add_argument(
            "--skip-until",
            required=False,
            type=int,
            default=0,
            help="Skip until, uses an id to skip processes",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        import_financial_disclosures(
            filepath=options["filepath"], skip_until=options["skip_until"]
        )
