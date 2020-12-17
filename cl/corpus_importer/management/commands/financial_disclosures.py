import json
from typing import Dict
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.crypto import sha1
from cl.people_db.models import (
    FinancialDisclosure,
    Person,
    Investment,
    Agreements,
    Debt,
    Gift,
    Reimbursement,
    NonInvestmentIncome,
    SpouseIncome,
    Positions,
)
from cl.scrapers.transformer_extractor_utils import get_page_count


def check_if_in_system(sha1_hash: str) -> bool:
    """Check if PDF in db already.

    :param sha1_hash: PDF sha1 hash
    :return: Whether PDF is in db.
    """
    disclosures = FinancialDisclosure.objects.filter(pdf_hash=sha1_hash)
    if len(disclosures) > 0:
        logger.info("PDF already in system")
        return True
    return False


def extract_content(pdf_bytes: bytes) -> Dict:
    """Extract the content of the PDF.

    Attempt extraction using multiple methods if necessary.

    :param pdf_bytes: The byte array of the PDF
    :return:The OCR'd PDF content
    """

    logger.info("Beginning Extraction")

    # Extraction takes between 7 seconds and 80 minutes for super
    # long Trump extraction with ~5k investments
    extractor_response = requests.post(
        settings.BTE_URLS["extract-disclosure"],
        files={"pdf_document": ("file", pdf_bytes)},
        timeout=60 * 120,
    )

    if (
        extractor_response.status_code != 200
        or extractor_response.json()["success"] is False
    ):
        # Try second method
        logger.info("Attempting second extraction")
        extractor_response = requests.post(
            settings.BTE_URLS["extract-disclosure-jw"],
            files={"file": ("file", pdf_bytes)},
            timeout=60 * 60,
        )

        if (
            extractor_response.status_code != 200
            or extractor_response.json()["success"] is False
        ):
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
        return FinancialDisclosure.INITIAL
    elif extracted_data.get("nomination"):
        return FinancialDisclosure.NOMINATION
    elif extracted_data.get("annual"):
        return FinancialDisclosure.ANNUAL
    elif extracted_data.get("final"):
        return FinancialDisclosure.FINAL


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
    with transaction.atomic():
        disclosure.has_been_extracted = True
        disclosure.addendum_content_raw = extracted_data[addendum]["text"]
        disclosure.addendum_redacted = extracted_data[addendum]["is_redacted"]
        disclosure.is_amended = extracted_data.get("amended") or False
        disclosure.report_type = get_report_type(extracted_data)
        disclosure.save()

        for investment in extracted_data["sections"]["Investments and Trusts"][
            "rows"
        ]:
            Investment.objects.create(
                financial_disclosure=disclosure,
                redacted=True
                in [v["is_redacted"] for _, v in investment.items()],
                description=investment["A"]["text"],
                has_inferred_values=investment["A"]["inferred_value"],
                income_during_reporting_period_code=investment["B1"]["text"],
                income_during_reporting_period_type=investment["B2"]["text"],
                gross_value_code=investment["C1"]["text"],
                gross_value_method=investment["C2"]["text"],
                transaction_during_reporting_period=investment["D1"]["text"],
                transaction_date_raw=investment["D2"]["text"],
                transaction_value_code=investment["D3"]["text"],
                transaction_gain_code=investment["D4"]["text"],
                transaction_partner=investment["D5"]["text"],
            )

        for agreement in extracted_data["sections"]["Agreements"]["rows"]:
            Agreements.objects.create(
                financial_disclosure=disclosure,
                redacted=True
                in [v["is_redacted"] for _, v in agreement.items()],
                date=agreement["Date"]["text"],
                parties_and_terms=agreement["Parties and Terms"]["text"],
            )

        for debt in extracted_data["sections"]["Liabilities"]["rows"]:
            Debt.objects.create(
                financial_disclosure=disclosure,
                redacted=True in [v["is_redacted"] for _, v in debt.items()],
                creditor_name=debt["Creditor"]["text"],
                description=debt["Description"]["text"],
                value_code=debt["Value Code"]["text"],
            )

        for position in extracted_data["sections"]["Positions"]["rows"]:
            Positions.objects.create(
                financial_disclosure=disclosure,
                redacted=True
                in [v["is_redacted"] for _, v in position.items()],
                position=position["Position"]["text"].replace("LL. ", ""),
                organization_name=position["Name of Organization"]["text"],
            )

        for gift in extracted_data["sections"]["Gifts"]["rows"]:
            Gift.objects.create(
                financial_disclosure=disclosure,
                source=gift["Source"]["text"],
                description=gift["Description"]["text"],
                value_code=gift["Value"]["text"],
                redacted=True in [v["is_redacted"] for _, v in gift.items()],
            )

        for reimbursement in extracted_data["sections"]["Reimbursements"][
            "rows"
        ]:
            if 5 != len(reimbursement.items()):
                # Just in case - probably not needed
                continue
            Reimbursement.objects.create(
                financial_disclosure=disclosure,
                redacted=True
                in [v["is_redacted"] for _, v in reimbursement.items()],
                source=reimbursement["Source"]["text"],
                dates=reimbursement["Dates"]["text"],
                location=reimbursement["Locations"]["text"],
                purpose=reimbursement["Purpose"]["text"],
                items_paid_or_provided=reimbursement["Items Paid or Provided"][
                    "text"
                ],
            )

        for non_investment_income in extracted_data["sections"][
            "Non-Investment Income"
        ]["rows"]:
            NonInvestmentIncome.objects.create(
                financial_disclosure=disclosure,
                redacted=True
                in [
                    v["is_redacted"] for _, v in non_investment_income.items()
                ],
                date=non_investment_income["Date"]["text"],
                source_type=non_investment_income["Source and Type"]["text"],
                income_amount=non_investment_income["Income"]["text"],
            )

        for spouse_income in extracted_data["sections"][
            "Non Investment Income Spouse"
        ]["rows"]:
            SpouseIncome.objects.create(
                financial_disclosure=disclosure,
                redacted=True
                in [v["is_redacted"] for _, v in spouse_income.items()],
                date=spouse_income["Date"]["text"],
                source_type=spouse_income["Source and Type"]["text"],
            )

        logger.info(
            f"Upload to https://{settings.AWS_S3_CUSTOM_DOMAIN}/"
            f"{disclosure.filepath}"
        )


def extract_pdf(data: dict) -> requests.Response:
    """Download or generate PDF content from images or urls.

    :param data: Data to process.
    :return: Response containing PDF
    """
    if data["disclosure_type"] == "jw":
        # Download the PDFs in the judicial watch collection
        logger.info(
            f"Preparing to process JW url: {quote(data['url'], safe=':/')}"
        )

        pdf_response = requests.get(data["url"], timeout=60 * 20)

    elif data["disclosure_type"] == "single":
        # Split single long tiff into multiple tiffs and combine into PDF
        logger.info(
            f"Preparing to process url: {quote(data['url'], safe=':/')}"
        )
        pdf_response = requests.post(
            settings.BTE_URLS["image-to-pdf"],
            params={"tiff_url": data["url"]},
            timeout=10 * 60,
        )
    else:
        # Combine split tiffs into one single PDF
        logger.info(
            f"Preparing to process split urls: "
            f"{quote(data['urls'][0], safe=':/')}"
        )

        pdf_response = requests.post(
            settings.BTE_URLS["urls-to-pdf"],
            json=json.dumps({"urls": data["urls"]}),
        )
    return pdf_response



def judicial_watch(options: Dict) -> None:
    """

    :param options:
    :type options: Dict
    :return:
    """
    filepath = options["filepath"]

    # url = ""
    # j = json.load(filepath)

    # -------------- ** ** ** *--------------
    # Temporary data

    filepath = "/opt/courtlistener/samples/sample_jw.json"
    with open(filepath) as f:
        disclosures = json.load(f)

    # -------------- ******* --------------

    for data in disclosures:
        person_id = data["person_id"]
        bucket = "com-courtlistener-storage.s3-us-west-2.amazonaws.com"
        aws_url = f"https://{bucket}/{data['path']}"
        pdf_bytes = requests.get(aws_url).content
        extractor_response = requests.post(
            settings.BTE_URLS["extract-disclosure"],
            files={"file": ("", pdf_bytes)},
            timeout=60 * 60,
        )
        # print(extractor_response.json())
        pprint.pprint(extractor_response.json())

        break


class Command(VerboseCommand):
    help = "Add financial disclosures to CL database."

    def valid_actions(self, s):
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s"
                % (", ".join(self.VALID_ACTIONS.keys()))
            )
        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser):
        parser.add_argument(
            "--action",
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s"
            % (", ".join(self.VALID_ACTIONS.keys())),
        )
        parser.add_argument(
            "--filepath",
            required=True,
            help="Filepath to json identifiy documents to process",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options["action"](options)

    VALID_ACTIONS = {
        "split-tiffs": split_tiffs,
        "single-tiff": single_tiff,
        "judicial-watch": judicial_watch,
    }
