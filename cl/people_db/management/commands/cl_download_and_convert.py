import os
import re
import argparse
import glob
import boto3
from botocore import UNSIGNED
from botocore.client import Config
from urllib import quote
import requests
from tempfile import NamedTemporaryFile

from PyPDF2 import PdfFileMerger, PdfFileReader, PdfFileWriter
from PIL import Image
from cl.scrapers.tasks import extract_by_ocr

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.utils import mkdir_p
from django.conf import settings
from cl.people_db.models import FinancialDisclosure, Person, Position

parent_url = "https://%s/" % settings.AWS_S3_CUSTOM_DOMAIN
bucket = settings.AWS_STORAGE_BUCKET_NAME
prefix = "financial-disclosures"


def combine_images_into_pdf(xlist, download_list):
    filename = os.path.basename(download_list[-1]) + ".pdf"
    assetdir = os.path.join(settings.MEDIA_ROOT, "financial-disclosures")
    mkdir_p(assetdir)
    filepath = os.path.join(assetdir, filename)
    im = xlist.pop(0)
    im.save(
        filepath, "PDF", resolution=100.0, save_all=True, append_images=xlist,
    )

    logger.info("Converted file: %s" % filepath)


def sorted_list_of_images(download_urls):
    key_pat = re.compile(r"(.*Page_)(.*)(\.tif)")

    def key(item):
        m = key_pat.match(item)
        return int(m.group(2))

    download_urls.sort(key=key)

    xlist = []
    for link in download_urls:
        img = Image.open(requests.get(link, stream=True).raw)
        xlist.append(img)
    return xlist


def split_single_image_into_image_list(download_urls):
    img = Image.open(requests.get(download_urls[0], stream=True).raw)
    width, height = img.size
    xlist = []
    i, page_width, page_height = 0, width, (1046 * (float(width) / 792))
    while i < (height / page_height):
        image = img.crop(
            (0, (i * page_height), page_width, (i + 1) * page_height)
        )
        xlist.append(image)
        i += 1
    return xlist


def process_pdf(download_urls, document_xkey_list):
    pdf_basename = os.path.basename(document_xkey_list[-1]) + ".pdf"
    pdf_path = os.path.join(
        settings.MEDIA_ROOT, "financial-disclosures", pdf_basename
    )
    if os.path.exists(pdf_path):
        logger.info("Already converted: %s" % pdf_path)
    else:
        logger.info("Converting %s" % document_xkey_list[-1])
        if len(download_urls) > 1:
            xlist = sorted_list_of_images(download_urls, document_xkey_list)
        else:
            xlist = split_single_image_into_image_list(
                download_urls, document_xkey_list
            )
        combine_images_into_pdf(xlist, document_xkey_list)


def get_section_info_by_ocr(filepath, page_num, lowerleft, upperright):
    fin = open(filepath, "rb")
    reader = PdfFileReader(fin)
    writer = PdfFileWriter()

    page = reader.getPage(page_num)

    page.cropBox.lowerLeft = lowerleft
    page.cropBox.upperRight = upperright
    page.mediaBox.lowerLeft = lowerleft
    page.mediaBox.upperRight = upperright

    writer.addPage(page)
    with NamedTemporaryFile(prefix="crop_", suffix=".pdf") as tmp:
        fout = open(tmp.name, "wb")
        writer.write(fout)
        is_extracted, content = extract_by_ocr(tmp.name)

    fin.close()

    return content


def download_new_disclosures(options):
    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    document_keys_to_process = []
    while True:
        resp = s3.list_objects_v2(**kwargs)

        for obj in resp["Contents"]:
            key = obj["Key"]

            if "Thumbs.db" in key:
                continue

            # Check if we have key, or want to use this key.
            document_urls_to_download = []
            if key.endswith("pdf"):
                # Judicial Watch PDF
                document_urls_to_download.append(parent_url + quote(key))
                xkey = os.path.splitext(key)[0]
                document_keys_to_process.append(xkey)

            elif "_Page" in key:
                # Older Pre-split TIFFs
                if key.split("_Page")[0] in document_keys_to_process:
                    continue
                xkey = key.split("_Page")[0]
                bundle_query = {"Bucket": bucket, "Prefix": xkey}
                second_response = s3.list_objects_v2(**bundle_query)
                for obj in second_response["Contents"]:
                    key = obj["Key"]
                    if "Thumbs.db" not in key:
                        document_urls_to_download.append(
                            parent_url + quote(key)
                        )
                document_keys_to_process.append(xkey)
            else:
                # Regular old Large TIFF
                xkey = os.path.splitext(key)[0]
                document_urls_to_download.append(parent_url + quote(key))
                document_keys_to_process.append(xkey)

            process_pdf(document_urls_to_download, document_keys_to_process)

        try:
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        except KeyError:
            break


def add_metadata_to_pdf(infilepath, outfilepath, info):

    fin = open(infilepath, "rb")
    reader = PdfFileReader(fin)
    writer = PdfFileWriter()

    writer.appendPagesFromReader(reader)
    metadata = reader.getDocumentInfo()
    writer.addMetadata(metadata)

    # Write your custom metadata here:
    writer.addMetadata(info)

    fout = open(outfilepath, "wb")
    writer.write(fout)

    fin.close()
    fout.close()
    if os.path.exists(infilepath):
        os.remove(infilepath)


def get_metadata_from_pdf(filepath):
    with open(filepath, "rb") as f:
        pdf = PdfFileReader(f)
        info = pdf.getDocumentInfo()
    print(info)
    return info


def get_page_count_ocr(im):
    pixel_width, pixel_height = 794, 1046
    pgnumber_coords = (0, 0, 320, 90)
    width, height = im.size
    nth_page = 2
    page_count_px = float(height) / pixel_height
    im_pg2 = get_nth_page(im, 2)
    im_pgnumber = im_pg2.crop(pgnumber_coords)
    with NamedTemporaryFile(prefix="pgnum_", suffix=".pdf") as tmp:
        im_pgnumber.save(tmp.name)
        is_extracted, content = extract_by_ocr(tmp.name)

    pagination = re.search("Page \d+ of \d+", content, flags=re.IGNORECASE)
    try:
        page_count_ocr = pagination.group().split()[3]
    except IndexError:
        page_count_ocr = None

    return page_count_ocr, page_count_px


def get_nth_page(im, n):
    pixel_width, pixel_height = 794, 1046
    width, height = im.size
    im_nth_page = im.crop((0, (n - 1) * pixel_height, width, n * pixel_height))
    return im_nth_page


def get_fd_year(key):
    subdir = os.path.relpath(key, start=prefix).split("/")[0]
    if subdir == "judicial-watch":
        subdir = re.search(r"\d{4}", key).group()
    year = subdir
    return year


def find_judge(item):
    fd_judge = None
    person = Person.objects.filter(
        name_first=item["name_first"],
        name_middle=item["name_middle"],
        name_last=item["name_last"],
        # name_suffix=item["name_suffix"],
    )

    if len(person) == 1:
        fd_judge = person[0]
    elif len(person) == 0:
        # no person found
        logger.info(
            "Judge not found: %s %s %s"
            % (item["name_first"], item["name_middle"], item["name_last"])
        )
    else:
        position = Position.objects.filter(
            person=person,
            position_type=item["position_type"],
            # job_title=item['job_title'],
            court=item["court"],
        )
        if len(position) == 1:
            fd_judge = position.person
        elif len(position) == 0:
            # No person found
            logger.info(
                "Judge not found: %s %s %s (%s, %s)"
                % (
                    item["name_first"],
                    item["name_middle"],
                    item["name_last"],
                    item["position_type"],
                    item["court"],
                )
            )
        else:
            logger.info(
                "Multiple judges found for %s %s %s"
                % (item["name_first"], item["name_middle"], item["name_last"])
            )
    return fd_judge


def add_file_to_db(item):
    fd = FinancialDisclosure(
        person=item["person"],
        year=item["year"],
        filepath=item["filepath"],
        thumbnail=item["thumbnail"],
        thumbnail_status=item["thumbnail_status"],
        page_count=item["page_count"],
    )
    fd.save()



class Command(VerboseCommand):
    help = "Download and save financial disclosures for processing."

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
            "--page_height",
            help="Page height in pixels",
            required=False,
            default=1046,
            type=int,
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options["action"](options)

    VALID_ACTIONS = {
        "download-files": download_new_disclosures,
        "assign-judges": add_judge_to_disclosure,
    }
