import boto3
import io
import re
import argparse
import requests
import PyPDF2
from PIL import Image
from botocore import UNSIGNED
from botocore.client import Config

from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.models import FinancialDisclosure, Person, Position

from django.conf import settings
from django.core.files.base import ContentFile

AWS_STORAGE_BUCKET_NAME = "com-courtlistener-storage"
parent_url = "https://%s/" % settings.AWS_S3_CUSTOM_DOMAIN
base_url = "http://com-courtlistener-storage.s3-us-west-2.amazonaws.com/"
prefix = "financial-disclosures"
jw_prefix = "financial-disclosures/judicial-watch"
s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))


def find_pk(fp):
    """

    :param fp:
    :return:
    """
    settings.DEBUG = False
    import csv

    with open("cl/corpus_importer/tmp/target.tsv") as tsvfile:
        reader = csv.reader(tsvfile, delimiter="\t")
        for row in reader:
            if row[1].strip() == fp.replace(
                "http://com-courtlistener-storage.s3-us-west-2.amazonaws.com/",
                "",
            ):
                if row[0].strip() == "xxx":
                    return False
                return row[0]


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


def get_year(key):
    """

    :param key:
    :return:
    """
    year_regex = re.compile(r".*\/([0-9]{4})\/.*")
    m = year_regex.match(key)
    year = m.group(1)
    return year


def download_convert_and_save(aws_path):
    """

    :param aws_path:
    :return:
    """
    resp = s3.list_objects_v2(
        **{"Bucket": AWS_STORAGE_BUCKET_NAME, "Prefix": aws_path[:-10]}
    )
    download_urls = [
        base_url + x["Key"] for x in resp["Contents"] if "db" not in x["Key"]
    ]
    if len(download_urls) == 0:
        # financial-disclosures/2012/A-H/Goldberg-MR. MP. 02. NYS   R_12/Thumbs.db
        # Must be empty-
        print "FAIL QUERY", aws_path
        return

    pk = find_pk(download_urls[0])

    if not pk:
        print "FAIL no ID", aws_path
        return

    key_pat = re.compile(r"(.*Page_)(.*)(\.tif)")

    def key(item):
        m = key_pat.match(item)
        return int(m.group(2))

    download_urls.sort(key=key)

    image_list = []
    for link in download_urls:
        image_list.append(Image.open(requests.get(link, stream=True).raw))

    pdf_data = make_pdf_from_image_array(image_list)
    fd = FinancialDisclosure()
    fd.year = get_year(key)
    fd.page_count = len(image_list)
    fd.person = Person.objects.get(pk=pk)
    fd.filepath.save("", ContentFile(pdf_data))


def parse_split_tiffs(options):
    """

    :param options:
    :return:
    """
    kwargs = {"Bucket": AWS_STORAGE_BUCKET_NAME, "Prefix": prefix}
    while True:
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp["Contents"]:
            aws_path = obj["Key"]
            if "Thumbs.db" not in aws_path:
                continue
            if len(aws_path.split("/")) == 4:
                continue
            if ".pdf" in aws_path:
                continue

            download_convert_and_save(aws_path)

        try:
            # break
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        except KeyError:
            break


def convert_long_image_to_pdf(aws_path, pk):
    """

    :param aws_path: AWS S3 Path
    :param pk: The Person ID in CL db
    :return:
    """
    img = Image.open(
        requests.get("%s%s" % (base_url, aws_path), stream=True).raw
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

    pdf_data = make_pdf_from_image_array(image_list)
    fd = FinancialDisclosure()
    fd.year = get_year(aws_path)
    fd.page_count = len(image_list)
    fd.person = Person.objects.get(id=pk)
    fd.filepath.save("", ContentFile(pdf_data))


def split_long_pdfs(options):
    """

    :param options:
    :return:
    """
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

            pk = find_pk(aws_path)
            if pk:
                convert_long_image_to_pdf(aws_path, pk)

            break

        try:
            # break
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        except KeyError:
            break


def judicial_watch(options):
    """

    :param options:
    :return:
    """
    kwargs = {"Bucket": AWS_STORAGE_BUCKET_NAME, "Prefix": jw_prefix}
    while True:
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp["Contents"]:
            aws_path = obj["Key"]
            pk = find_pk(aws_path)
            year = aws_path.split(" ")[-1][:4]

            if pk:
                link = base_url + aws_path
                response = requests.get(link)

                with io.BytesIO(response.content) as open_pdf_file:
                    pdf_data = PyPDF2.PdfFileReader(open_pdf_file)
                    num_pages = pdf_data.getNumPages()

                fd = FinancialDisclosure()
                fd.year = year
                fd.page_count = num_pages
                fd.person = Person.objects.get(id=pk)
                fd.filepath.save("", ContentFile(response.content))
                logger.info(
                    "Saved pdf at : %s",
                    (
                        "https://dev-com-courtlistener-storage.s3-us-west-2.amazonaws.com"
                        + str(fd.filepath)
                    ),
                )

            else:
                logger.info("Missing judge for filepath: %s", aws_path)
        try:
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

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options["action"](options)

    VALID_ACTIONS = {
        "split-tiff": parse_split_tiffs,
        "long-tiffs": split_long_pdfs,
        "jw": judicial_watch,
    }
