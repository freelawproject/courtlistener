import csv

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


def make_key_path_dictionary(options):
    """Generate our lookup dictionary

    :param options:
    :return: dictionary of url to judge PKs
    """
    lookup_dict = {}
    with open(options['tsv_path']) as tsvfile:
        reader = csv.reader(tsvfile, delimiter="\t")
        for row in reader:
            # print row
            lookup_dict[row[1].strip()] = row[0].strip()
    return lookup_dict



def find_pk(fp):
    """ Lookup PK of judge based on AWS url

    :param fp: AWS URL path
    :return: PK of judge in DB
    """
    settings.DEBUG = False
    import csv

    with open("cl/corpus_importer/tmp/target.tsv") as tsvfile:
        reader = csv.reader(tsvfile, delimiter="\t")
        for row in reader:
            if row[1].strip() == fp.split("/", 3)[-1]:
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


def get_year(aws_url_path):
    """ Parse Year of FD from AWS url

    :param aws_url_path:
    :return:
    """
    year_regex = re.compile(r".*\/([0-9]{4})\/.*")
    m = year_regex.match(aws_url_path)
    year = m.group(1)
    return year


def download_convert_and_save(aws_url_path):
    """
    :param aws_url_path:
    :return:
    """
    resp = s3.list_objects_v2(
        **{"Bucket": AWS_STORAGE_BUCKET_NAME, "Prefix": aws_url_path[:-10]}
    )
    download_urls = [
        base_url + x["Key"] for x in resp["Contents"] if "db" not in x["Key"]
    ]
    if len(download_urls) == 0:
        # financial-disclosures/2012/A-H/Goldberg-MR. MP. 02. NYS   R_12/Thumbs.db
        # Must be empty-
        print "FAIL QUERY", aws_url_path
        return

    pk = find_pk(download_urls[0])

    if not pk:
        print "FAIL no ID", aws_url_path
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

    save_and_upload_fd(
        year=get_year(aws_url_path),
        page_count=len(image_list),
        pk=pk,
        pdf_data=pdf_data
    )


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


def convert_long_image_to_pdf(aws_url_path, pk):
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

    save_and_upload_fd(
        year=get_year(aws_url_path),
        page_count=len(image_list),
        pk=pk,
        pdf_data=make_pdf_from_image_array(image_list)
    )


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

    lookup_dict = make_key_path_dictionary(options)

    kwargs = {"Bucket": AWS_STORAGE_BUCKET_NAME, "Prefix": jw_prefix}
    while True:
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp["Contents"]:
            aws_path = obj["Key"]
            pk = lookup_dict[aws_path]
            if not pk or pk == "xxx":
                logger.info("Missing judge for filepath: %s", aws_path)
                continue

            pdf_url = "http://com-courtlistener-storage.s3-us-west-2.amazonaws.com/%s" % aws_path
            response = requests.get(pdf_url)

            with io.BytesIO(response.content) as open_pdf_file:
                pdf_data = PyPDF2.PdfFileReader(open_pdf_file)
                num_pages = pdf_data.getNumPages()

            save_and_upload_fd(
                year=aws_path.split(" ")[-1][:4],
                page_count=num_pages,
                pk=pk,
                pdf_data=response.content
            )

        try:
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        except KeyError:
            break


def save_and_upload_fd(year, page_count, pk, pdf_data):
    """

    :param year:
    :param page_count:
    :param pk:
    :param pdf_data:
    :return:
    """

    fd = FinancialDisclosure()
    fd.year = year
    fd.page_count = page_count
    fd.person = Person.objects.get(id=pk)
    fd.filepath.save("", ContentFile(pdf_data))

    logger.info(
        "Saved pdf to : %s",
        (
            "https://dev-com-courtlistener-storage.s3-us-west-2.amazonaws.com"
            + str(fd.filepath)
        ),
    )


def test(options):


    # print "https://dev-com-courtlistener-storage.s3-us-west-2.amazonaws.com/asdfa/asdf/asdf".split("/", 3)
    # print options['tsv_path']
    # lookup_dict = make_key_path_dictionary(options)
    kwargs = {"Bucket": AWS_STORAGE_BUCKET_NAME, "Prefix": jw_prefix}
    while True:
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp["Contents"]:
            aws_path = obj["Key"]
            print obj

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
            "--tsv-path",
            required=True,
            help="AWS Path to PK db",
        )


    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options["action"](options)

    VALID_ACTIONS = {
        "split-tiff": parse_split_tiffs,
        "long-tiffs": split_long_pdfs,
        "jw": judicial_watch,
        "test": test,
    }
