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

from io import BytesIO, StringIO
from PyPDF2 import PdfFileMerger, PdfFileReader, PdfFileWriter
from PIL import Image
from cl.scrapers.tasks import extract_by_ocr

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.utils import mkdir_p
from django.conf import settings
from cl.people_db.models import FinancialDisclosure, Person, Position

parent_url = "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/"
bucket = "com-courtlistener-storage"
prefix = "financial-disclosures"


def assemble_pdf(xlist, download_list):
    filename = os.path.basename(download_list[-1]) + ".pdf"
    assetdir = os.path.join(settings.MEDIA_ROOT, "financial-disclosures")
    mkdir_p(assetdir)
    filepath = os.path.join(assetdir, filename)
    im = xlist.pop(0)
    im.save(
        filepath, "PDF", resolution=100.0, save_all=True, append_images=xlist,
    )

    lastpage = xlist[-1]
    content = get_judge_info_ocr(lastpage, (0, 350, 700, 400))
    fullname = clean_judge_name(content)

    logger.info("Full name extracted by OCR: %s" % fullname)

    title = get_judge_info_ocr(im, (41, 196, 195, 215))
    logger.info("Title extracted by OCR: %s", title)

    court = get_judge_info_ocr(im, (345, 130, 500, 145))
    logger.info("Court extracted by OCR: %s", court)

    location = get_judge_info_ocr(im, (45, 289, 185, 300))
    logger.info("Location extracted by OCR: %s", location)

    logger.info("Converted file: %s" % filepath)


def sorted_list_of_images(download_urls, download_list):
    key_pat = re.compile(r"(.*Page_)(.*)(\.tif)")

    def key(item):
        m = key_pat.match(item)
        return int(m.group(2))

    download_urls.sort(key=key)

    xlist = []
    for link in download_urls:
        img = Image.open(requests.get(link, stream=True).raw)
        xlist.append(img)
    assemble_pdf(xlist, download_list)


def grab_and_split_image(download_urls, download_list):
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
    assemble_pdf(xlist, download_list)


def create_pdf(download_urls, download_list):
    pdf_basename = os.path.basename(download_list[-1]) + ".pdf"
    pdf_path = os.path.join(
        settings.MEDIA_ROOT, "financial-disclosures", pdf_basename
    )
    if os.path.exists(pdf_path):
        logger.info("Already converted: %s" % pdf_path)
    else:
        if len(download_urls) > 1:
            sorted_list_of_images(download_urls, download_list)
        else:
            grab_and_split_image(download_urls, download_list)
    return pdf_path


def get_section_info_by_ocr(
    filepath, page_num, lowerleft, upperright
):
    pixel_width, pixel_height = 794, 1046
    fin = open(filepath, "rb")
    reader = PdfFileReader(fin)
    writer = PdfFileWriter()

    page = reader.getPage(page_num)

    width_ratio = float(page.mediaBox.getWidth()) / pixel_width
    height_ratio = float(page.mediaBox.getHeight()) / pixel_height

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


def iterate_over_aws():
    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    download_list = []
    while True:
        resp = s3.list_objects_v2(**kwargs)

        for obj in resp["Contents"]:
            key = obj["Key"]

            if "Thumbs.db" in key:
                continue

            # Check if we have key, or want to use this key.
            download_urls = []
            if key.endswith("pdf"):
                # Judicial Watch PDF
                download_urls.append(parent_url + quote(key))
                xkey = os.path.splitext(key)[0]
                download_list.append(xkey)
                # cd['type'] = "pdf"
                # cd['urls'] = download_urls

            elif "_Page" in key:
                # Older Pre-split TIFFs
                if key.split("_Page")[0] in download_list:
                    continue
                xkey = key.split("_Page")[0]
                bundle_query = {"Bucket": bucket, "Prefix": xkey}
                second_response = s3.list_objects_v2(**bundle_query)
                for obj in second_response["Contents"]:
                    key = obj["Key"]
                    if "Thumbs.db" not in key:
                        download_urls.append(parent_url + quote(key))
                download_list.append(xkey)
            else:
                # Regular old Large TIFF
                xkey = os.path.splitext(key)[0]
                download_urls.append(parent_url + quote(key))
                download_list.append(xkey)

            pdf_path = create_pdf(download_urls, download_list)
            # TODO: grab the judge names, locations
            fullname = get_section_info_by_ocr(
                pdf_path, 5, (345, 1045-390), (600, 1045-345)
            )
            logger.info("Fullname %s: %s" % (pdf_path, fullname))

            # TODO: OCR signature page to get a better name
            # TODO: add metadata into the PDF here

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

    # get_metadata_from_pdf(outfilepath)


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


def get_judge_info_ocr(im, boundary):
    with NamedTemporaryFile(prefix="crop_", suffix=".pdf") as tmp:
        infocrop = im.crop(boundary)
        infocrop.save(tmp.name)
        is_extracted, content = extract_by_ocr(tmp.name)
    return content


def clean_judge_name(namestring):
    try:
        fullname = namestring.split("/")[1].split("\\")[0].strip()
    except:
        fullname = None
    return fullname


def get_nth_page(im, n):
    pixel_width, pixel_height = 794, 1046
    width, height = im.size
    im_nth_page = im.crop((0, (n - 1) * pixel_height, width, n * pixel_height))
    return im_nth_page


def get_fd_year(key, prefix):
    subdir = os.path.relpath(key, start=prefix).split("/")[0]
    if subdir == "judicial-watch":
        subdir = re.search(r"\d{4}", key).group()
    year = subdir
    return year


def create_judge(item):
    person = Person(
        name_first=item["name_first"], name_last=item["name_last"],
    )
    return person


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
        fd_judge = create_judge(item)
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
            fd_judge = create_judge(item)
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


def download_new_disclosures(options):
    iterate_over_aws()


def add_judge_to_disclosure(options):
    disclosures = []
    for doc in glob.iglob(
        os.path.join(settings.MEDIA_ROOT, "financial-disclosures", "*.pdf")
    ):
        item = {}
        pdf = PdfFileReader(open(doc, "rb"))
        item["page_count"] = pdf.getNumPages()
        item["filepath"] = doc
        # TODO: get name, year
        print(item)
        disclosures.append(item)


def upload_pdfs(options):
    pattern = os.path.join(
        settings.MEDIA_ROOT, "financial-disclosures/**/*.pdf"
    )
    for filepath in glob.iglob(pattern):
        logger.info("Uploading: %s", filepath)
        # TODO: upload PDF


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
        "upload-pdfs": upload_pdfs,
    }
