import argparse
import csv
import io
import re

import PyPDF2
import boto3
import requests
from PIL import Image
from botocore import UNSIGNED
from botocore.client import Config
from django.conf import settings
from django.core.files.base import ContentFile

from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.models import FinancialDisclosure, Person

AWS_STORAGE_BUCKET_NAME = "com-courtlistener-storage"
parent_url = "https://%s/" % settings.AWS_S3_CUSTOM_DOMAIN
base_url = "http://com-courtlistener-storage.s3-us-west-2.amazonaws.com/"
prefix = "financial-disclosures"
jw_prefix = "financial-disclosures/judicial-watch"
s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))


def make_key_path_dictionary(filepath):
    """Generate our lookup dictionary

    :param options:
    :return: dictionary of url to judge PKs
    """
    lookup_dict = {}
    with open(filepath) as tsvfile:
        reader = csv.reader(tsvfile)
        next(reader)
        for row in reader:
            lookup_dict[row[0].strip().replace("  ", " ")] = row[1].strip()
    return lookup_dict


def make_pdf_from_image_array(image_list):
    """

    :param image_list:
    :return:
    """
    with io.BytesIO() as output:
        image_list[0].save(
            output,
            "PDF",
            resolution=100.0,
            save_all=True,
            append_images=image_list[1:],
        )
        pdf_data = output.getvalue()

    return pdf_data


def get_year_from_url(aws_url_path):
    """ Parse Year of FD from AWS url

    :param aws_url_path:
    :return:
    """
    year_regex = re.compile(r".*\/([0-9]{4})\/.*")
    m = year_regex.match(aws_url_path)
    year = m.group(1)
    return year


def query_thumbs_db(aws_url):
    kwargs = {"Bucket": AWS_STORAGE_BUCKET_NAME, "Prefix": aws_url[:-10]}
    thumbs_db_query = s3.list_objects_v2(**kwargs)
    download_urls = [
        base_url + x["Key"]
        for x in thumbs_db_query["Contents"]
        if "db" not in x["Key"]
    ]
    page_regex = re.compile(r"(.*Page_)(.*)(\.tif)")

    def key(item):
        m = page_regex.match(item)
        return int(m.group(2))

    download_urls.sort(key=key)

    return download_urls, thumbs_db_query["Contents"][0]["Key"]


def convert_long_image_to_pdf(aws_url_path):
    """
    :param aws_url_path: AWS S3 Path
    :param pk: The Person ID in CL db
    :return:
    """

    img = Image.open(
        requests.get("%s%s" % (base_url, aws_url_path), stream=True).raw
    )
    width, height = img.size
    image_list = []
    i, page_width, page_height = 0, width, (1046 * (float(width) / 792))
    while i < (height / page_height):
        image = img.crop(
            (0, (i * page_height), page_width, (i + 1) * page_height)
        )
        image_list.append(image)
        i += 1
    return image_list


def parse_split_tiffs(options):
    """Find pre-split-tiffs and merge into a PDF

    The server is full of presplit tiffs, which can be identified by the
    Thumbs.db file. We can use the thumbs.db to organize how we query as to
    avoid any messing parsing.

    :param aws_dict: A dictionary of urls to judges in our system.
    :type aws_dict: dict
    :return: None
    """
    aws_dict = make_key_path_dictionary(options["csv_path"])

    kwargs = {"Bucket": AWS_STORAGE_BUCKET_NAME, "Prefix": prefix}
    while True:
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp["Contents"]:
            aws_path = obj["Key"]
            if "Thumbs.db" not in aws_path:
                continue

            sorted_urls, lookup = query_thumbs_db(aws_path)
            judge_pk = aws_dict[lookup]

            image_list = []
            for link in sorted_urls:
                image_list.append(
                    Image.open(requests.get(link, stream=True).raw)
                )
            pdf_content = make_pdf_from_image_array(image_list)

            fd = FinancialDisclosure(
                year=get_year_from_url(aws_path),
                page_count=len(image_list),
                person=Person.objects.get(id=judge_pk),
                person_id=judge_pk,
            )
            fd.filepath.save("", ContentFile(pdf_content))

        try:
            break
            # Add the continuation token to continue iterating
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        except KeyError:
            # If no continuation token we have reached the end and break
            break


def split_long_pdfs(options):
    """
    :param options:
    :return:
    """
    aws_dict = make_key_path_dictionary(options["csv_path"])
    kwargs = {"Bucket": AWS_STORAGE_BUCKET_NAME, "Prefix": prefix}
    while True:
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp["Contents"]:
            aws_path = obj["Key"]
            if "Thumbs.db" in aws_path:
                continue
            if "Page" in aws_path:
                continue
            if ".pdf" in aws_path:
                continue

            judge_pk = aws_dict[aws_path]
            image_list = convert_long_image_to_pdf(aws_url_path=aws_path)
            pdf_content = make_pdf_from_image_array(image_list)

            fd = FinancialDisclosure(
                year=get_year_from_url(aws_path),
                page_count=len(image_list),
                person=Person.objects.get(id=judge_pk),
                person_id=judge_pk,
            )
            fd.filepath.save("", ContentFile(pdf_content))

        try:
            # break
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        except KeyError:
            break


def judicial_watch(options):
    """

    :param aws_dict:
    :return:
    """
    aws_dict = make_key_path_dictionary(options["csv_path"])
    kwargs = {"Bucket": AWS_STORAGE_BUCKET_NAME, "Prefix": jw_prefix}
    while True:
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp["Contents"]:
            aws_path = obj["Key"]
            lookup_key = aws_path.replace("  ", " ")
            judge_pk = aws_dict[lookup_key]

            pdf_content = requests.get("%s%s" % (base_url, aws_path)).content
            with io.BytesIO(pdf_content) as open_pdf_file:
                pdf_data = PyPDF2.PdfFileReader(open_pdf_file)
                page_count = pdf_data.getNumPages()
            year = aws_path.split(" ")[-1][:4]

            fd = FinancialDisclosure(
                year=year,
                page_count=page_count,
                person=Person.objects.get(id=judge_pk),
                person_id=judge_pk,
            )
            print fd.filepath
            # break
            fd.filepath.save("", ContentFile(pdf_content))
            break
        try:
            break
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        except KeyError:
            break



class Command(VerboseCommand):
    help = "Convert Financial Disclousures into PDFs and add to db"

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
            "--csv-path",
            default="cl/corpus_importer/tmp/target_pkupdated.csv",
            required=False,
            help="AWS Path to PK db",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options["action"](options)

    VALID_ACTIONS = {
        "split-tiff": parse_split_tiffs,
        "long-tiffs": split_long_pdfs,
        "judicial-watch": judicial_watch,
    }
