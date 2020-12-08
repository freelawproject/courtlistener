import argparse
import json
import pprint
import re
from typing import Dict

import requests
from django.conf import settings
from django.core.files.base import ContentFile

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.crypto import sha1
from cl.people_db.models import FinancialDisclosure, Person
from cl.scrapers.transformer_extractor_utils import get_page_count


def split_tiffs(options: Dict) -> None:
    """Combine multiple page tiffs in a directory into one single PDF and extract the content.

    :param options:
    :type options: Dict
    :return:
    """
    filepath = options["filepath"]
    filepath = "/opt/courtlistener/samples/sample_all_pages.json"

    with open(filepath) as f:
        disclosures = json.load(f)

    for data in disclosures:
        bucket = "storage.courtlistener.com"
        path = data["key"]
        urls = [f"https://{bucket}/{path}/{p}" for p in data["paths"]]
        year = re.findall("20[1,2][0-9]", path)[0]

        logger.info(f"\nProcessing images")

        pdf_response = requests.post(
            settings.BTE_URLS["urls-to-pdf"],
            json=json.dumps({"urls": urls}),
        )

        if pdf_response.status_code is not 200:
            logger.info(f"\nConversion failed")
            continue

        sha1_hash = sha1(pdf_response.content)
        logger.info(f"\nConversion to PDF completed. \nBeginning extraction.")

        # Check if file exists
        disclsoures = FinancialDisclosure.objects.filter(pdf_hash=sha1_hash)
        if len(disclsoures) > 0:
            logger.info("PDF already in system")
            continue

        # Save and upload PDF to AWS (currently local machine)
        fd = FinancialDisclosure(
            year=year,
            page_count=get_page_count(pdf_response.content),
            person=Person.objects.get(id=1), # Will save to the same folder beacuse weve idenitifeid same year and same single person in our database.
            pdf_hash=sha1_hash,
        )
        print(fd.filepath)
        fd.filepath.save("", ContentFile(pdf_response.content))

        logger.info(
            "Uploading disclosure to https://%s/%s"
            % (settings.AWS_S3_CUSTOM_DOMAIN, fd.filepath)
        )

        continue

        extractor_response = requests.post(
            settings.BTE_URLS["extract-disclosure"],
            files={"file": ("", pdf_response.content)},
            timeout=60 * 60,
        )
        if extractor_response.status_code is not 200:
            logger.info(f"\nExtraction failed")
            continue

        logger.info("\nProcessing extracted data")
        print(extractor_response)
        print(extractor_response.json())

        break


def single_tiff(options: Dict) -> None:
    """

    :param options:
    :type options: Dict
    :return:
    """
    filepath = options["filepath"]
    disclosures = [
        {
            "path": "Urbanski-MF.%20J3.%2004.%20VAW%20_SPE_R_18.tiff",
            "key": "financial-disclosures/2018",
            "person_id": "3289",
        }
    ]

    filepath = "/opt/courtlistener/samples/sample_single.json"
    with open(filepath) as f:
        disclosures = json.load(f)

    # https://storage.courtlistener.com/financial-disclosures/2018/Urbanski-MF.%20J3.%2004.%20VAW%20_SPE_R_18.tiff
    for data in disclosures:
        person_id = data["person_id"]
        bucket = "com-courtlistener-storage.s3-us-west-2.amazonaws.com"
        path = data["key"]
        tiff_url = f"https://{bucket}/{path}/{data['path']}"

        logger.info(f"Preparing to process url: {tiff_url}")
        pdf_response = requests.post(
            settings.BTE_URLS["image-to-pdf"],
            params={"tiff_url": tiff_url},
            timeout=5 * 60,
        )
        logger.info(f"Conversion completed. \n Beginning Extraction")
        extractor_response = requests.post(
            settings.BTE_URLS["extract-disclosure"],
            files={"file": ("", pdf_response.content)},
            timeout=60 * 60,
        )

        logger.info("Processing extracted data")
        pprint.pprint(extractor_response.json())

        break


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
