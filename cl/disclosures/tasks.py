import datetime
from typing import Optional, Union

import requests
from asgiref.sync import async_to_sync
from dateutil.parser import ParserError, parse
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from redis import ConnectionError as RedisConnectionError
from redis import Redis
from requests import Response
from requests.exceptions import RequestException

from cl.celery_init import app
from cl.disclosures.models import (
    REPORT_TYPES,
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
from cl.lib.command_utils import logger
from cl.lib.crypto import sha1
from cl.lib.microservice_utils import microservice
from cl.lib.models import THUMBNAIL_STATUSES
from cl.lib.redis_utils import create_redis_semaphore, get_redis_interface


def make_disclosure_key(data_id: str) -> str:
    """Make disclosure key to use with redis

    :param data_id: The ID of the document being processed
    :return: Disclosure key
    """
    return f"disclosure.enqueued:fd-{data_id}"


@app.task(bind=True, max_retries=2, ignore_result=True)
@transaction.atomic
def make_financial_disclosure_thumbnail_from_pdf(self, pk: int) -> None:
    """Generate Thumbnail and save to AWS

    Attempt to generate thumbnail from PDF and save to AWS.

    :param self: The celery task
    :param pk: PK of disclosure in database
    :return: None
    """
    disclosure = FinancialDisclosure.objects.select_for_update().get(pk=pk)
    pdf_content = disclosure.filepath.read()

    response = async_to_sync(microservice)(
        service="generate-thumbnail",
        file_type="pdf",
        file=pdf_content,
    )
    if not response.is_success:
        if self.request.retries == self.max_retries:
            disclosure.thumbnail_status = THUMBNAIL_STATUSES.FAILED
            disclosure.save()
            return
        else:
            raise self.retry(exc=response.status_code)

    disclosure.thumbnail_status = THUMBNAIL_STATUSES.COMPLETE
    disclosure.thumbnail.save(None, ContentFile(response.content))


def extract_content(
    pdf_bytes: bytes,
    disclosure_key: str,
) -> dict[str, Union[str, int]]:
    """Extract the content of the PDF.

    Attempt extraction using multiple methods if necessary.

    :param pdf_bytes: The byte array of the PDF
    :param disclosure_key: The disclosure ID
    :return:The extracted content
    """
    logger.info("Attempting extraction.")

    # Extraction takes between 7 seconds and 80 minutes for super
    # long Trump extraction with ~5k investments
    response = async_to_sync(microservice)(
        service="extract-disclosure",
        file_type="pdf",
        file=pdf_bytes,
    )

    if not response.is_success:
        logger.warning(
            msg="Could not extract data from this document",
            extra=dict(
                disclosure_key=disclosure_key, status=response.status_code
            ),
        )
        return {}

    logger.info("Processing extracted data")
    return response.json()


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
                value_code=(
                    debt["Value Code"]["text"]
                    if debt["Value Code"]["text"] != "None"
                    else ""
                ),
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


def save_and_upload_disclosure(
    redis_db: Redis,
    disclosure_key: str,
    response: Response,
    data: dict,
) -> Optional[FinancialDisclosure]:
    """Save disclosure PDF to S3 and generate a FinancialDisclosure object.

    :param redis_db: The redis db storing our disclosure keys
    :param disclosure_key: The disclosure key for the redis db
    :param response: The pdf data response object
    :param data: The judge data as a dict
    :return: Financial discsosure object or None
    """
    sha1_hash = sha1(response.content)
    disclosure = FinancialDisclosure.objects.filter(sha1=sha1_hash)
    if len(disclosure) > 0:
        return disclosure[0]

    page_count = async_to_sync(microservice)(
        service="page-count",
        file_type="pdf",
        file=response.content,
    ).text
    if not page_count:
        logger.error(
            msg="Page count failed",
            extra={"disclosure_id": disclosure_key, "url": data["url"]},
        )

    # Make disclosure
    disclosure = FinancialDisclosure(
        year=int(data["year"]),
        page_count=page_count,
        person_id=data["person_id"],
        sha1=sha1_hash,
        has_been_extracted=False,
        report_type=data.get("report_type", REPORT_TYPES.UNKNOWN),
        download_filepath=data.get("url"),
    )

    # Save method here uploads the file to s3 and also triggers thumbnail
    # generation in the background via the save method in disclosure.models
    disclosure.filepath.save(
        f"{disclosure.person.slug}-disclosure.{data['year']}.pdf",
        ContentFile(response.content),
    )
    logger.info(
        f"Uploaded to https://{settings.AWS_S3_CUSTOM_DOMAIN}/"
        f"{disclosure.filepath}"
    )
    return disclosure


@app.task(
    bind=True,
    autoretry_for=(RequestException, RedisConnectionError),
    max_retries=2,
    interval_start=10,
    ignore_result=True,
)
def import_disclosure(self, data: dict[str, Union[str, int, list]]) -> None:
    """Import disclosures into Courtlistener

    :param data: The disclosure information to process
    :return: None
    """
    redis_db = get_redis_interface("CACHE")
    disclosure_key = make_disclosure_key(data["id"])
    newly_enqueued = create_redis_semaphore(
        redis_db,
        disclosure_key,
        ttl=60 * 60 * 2,
    )

    if not newly_enqueued:
        logger.info(
            f"Process is already running {data['id']}. {disclosure_key}",
        )
        return

    logger.info(
        f"Processing row {data['id']} for person {data['person_id']} "
        f"in year {data['year']}"
    )
    response = requests.get(data["url"], timeout=60 * 20)

    if not response.ok:
        logger.error(
            f"Failed to download {data['id']} {data['url']}",
            extra={"disclosure_id": data["id"]},
        )
        redis_db.delete(disclosure_key)
        return

    # Check if disclosure already exists
    query = FinancialDisclosure.objects.filter(download_filepath=data["url"])
    if len(query) > 0:
        # If previously uploaded, use disclosure else process new document
        disclosure = query[0]
    else:
        disclosure = save_and_upload_disclosure(
            redis_db, disclosure_key, response, data
        )
        if not disclosure:
            logger.error(
                f"Disclosure failed to save or upload to aws {data['id']} {data['url']}",
                extra={"disclosure_id": data["id"]},
            )
            return

    # Extract content from PDF
    content = extract_content(
        pdf_bytes=response.content,
        disclosure_key=disclosure_key,
    )
    if not content:
        redis_db.delete(disclosure_key)
        return

    # Save PDF content
    try:
        save_disclosure(extracted_data=content, disclosure=disclosure)
    except IntegrityError:
        logger.exception(
            f"Integrity error on saving disclosure {data['id']} {data['url']}",
            extra={"disclosure_id": data["id"]},
        )
    except ValidationError:
        logger.exception(
            "Validation Error up saving disclosure",
            extra={"disclosure_id": data["id"]},
        )

    # Remove disclosure ID in redis for completed disclosure
    redis_db.delete(disclosure_key)
