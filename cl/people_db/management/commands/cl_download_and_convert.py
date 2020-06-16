import os
import re
import argparse
import glob
import boto3
from botocore import UNSIGNED
from botocore.client import Config
from urllib import quote
import requests

from io import BytesIO, StringIO
from PyPDF2 import PdfFileMerger, PdfFileReader
from PIL import Image
import textract

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.utils import mkdir_p
from django.conf import settings
from cl.people_db.models import FinancialDisclosure


class FD(object):
    def __init__(self):
        self.s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        self.bucket = "com-courtlistener-storage"
        self.prefix = "financial-disclosures"
        # self.prefix = "financial-disclosures/2014/A-F/Collings-RB"
        # self.prefix = "financial-disclosures/2011/A-E/Aldisert-RJ/Aldisert-RJ"
        # self.prefix = "financial-disclosures/2011/A-E/Albritton-WH. J3. 11. ALM. resp.tiff"
        self.kwargs = {"Bucket": self.bucket, "Prefix": self.prefix}
        self.parent_url = (
            "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/"
        )
        self.download_list = []
        self.download_urls = []

    def sorted_list_of_images(self):
        key_pat = re.compile(r"(.*Page_)(.*)(\.tif)")

        def key(item):
            m = key_pat.match(item)
            return int(m.group(2))

        self.download_urls.sort(key=key)

        xlist = []
        for link in self.download_urls:
            img = Image.open(requests.get(link, stream=True).raw)
            xlist.append(img)
        self.assemble_pdf(xlist)

    def grab_and_split_image(self):
        img = Image.open(requests.get(self.download_urls[0], stream=True).raw)
        width, height = img.size
        xlist = []
        i, page_width, page_height = 0, width, (1046 * (width / 792))
        while i < (height / page_height):
            image = img.crop(
                (0, (i * page_height), page_width, (i + 1) * page_height)
            )
            xlist.append(image)
            i += 1
        self.assemble_pdf(xlist)

    def assemble_pdf(self, xlist):
        filename = os.path.basename(self.download_list[-1]) + ".pdf"
        assetdir = os.path.join(settings.MEDIA_ROOT, "financial-disclosures")
        mkdir_p(assetdir)
        filepath = os.path.join(assetdir, filename)
        im = xlist.pop(0)
        im.save(
            filepath,
            "PDF",
            resolution=100.0,
            save_all=True,
            append_images=xlist,
        )
        logger.info("Converted file: %s" % filepath)

    def create_pdf(self):
        pdf_basename = os.path.basename(self.download_list[-1]) + ".pdf"
        pdf_path = os.path.join(
            settings.MEDIA_ROOT, "financial-disclosures", pdf_basename
        )
        if os.path.exists(pdf_path):
            logger.info("Already converted: %s" % pdf_path)
        else:
            if len(self.download_urls) > 1:
                self.sorted_list_of_images()
            else:
                if not self.download_urls[0].endswith("pdf"):
                    self.grab_and_split_image()

    def iterate_over_aws(self):
        while True:
            resp = self.s3.list_objects_v2(**self.kwargs)

            for obj in resp["Contents"]:
                key = obj["Key"]

                if "Thumbs.db" in key:
                    continue

                # Check if we have key, or want to use this key.
                self.download_urls = []
                if key.endswith("pdf"):
                    # Judicial Watch PDF
                    self.download_urls.append(self.parent_url + quote(key))
                    xkey = os.path.splitext(key)[0]
                    self.download_urls.append(self.parent_url + quote(key))
                    self.download_list.append(xkey)
                    # cd['type'] = "pdf"
                    # cd['urls'] = download_urls

                elif "Page_" in key:
                    # Older Pre-split TIFFs
                    if key.split("Page")[0] in self.download_list:
                        continue
                    # if "2014/A-F/Collings-RB" in key:
                    #     xkey = "financial-disclosures/2014/A-F/Collings-RB"
                    # else:
                    #     xkey = key.split("Page")[0]
                    xkey = key.split("_Page")[0]
                    bundle_query = {"Bucket": self.bucket, "Prefix": xkey}
                    second_response = self.s3.list_objects_v2(**bundle_query)
                    for obj in second_response["Contents"]:
                        key = obj["Key"]
                        if "Thumbs.db" not in key:
                            self.download_urls.append(
                                self.parent_url + quote(key)
                            )
                    self.download_list.append(xkey)
                else:
                    # Regular old Large TIFF
                    xkey = os.path.splitext(key)[0]
                    self.download_urls.append(self.parent_url + quote(key))
                    self.download_list.append(xkey)

                # print(len(self.download_urls))
                # print(self.download_urls)
                # print(self.download_list)

                self.create_pdf()

                # HEre we have one PDF

                # Everything is the same here... one pdf to process
                # OCR the docuemnt, grab the judge names the locations
                # Ocr the LAST page - signature page to get a better name, or both
                # At teh metadata into the PDF here

                break

            try:
                self.kwargs["ContinuationToken"] = resp[
                    "NextContinuationToken"
                ]
            except KeyError:
                break


def get_page_count_ocr(im):
    pixel_width, pixel_height = 794, 1046
    pgnumber_coords = (0, 0, 320, 90)
    width, height = im.size
    nth_page = 2
    page_count_px = float(height) / pixel_height
    im_pg2 = get_nth_page(im, 2)
    im_pgnumber = im_pg2.crop(pgnumber_coords)
    im_pgnumber.save("pgnum.png")
    content = str(textract.process("pgnum.png", method="tesseract"))
    pagination = re.search("Page \d+ of \d+", content, flags=re.IGNORECASE)
    try:
        page_count_ocr = pagination.group().split()[3]
    except IndexError:
        page_count_ocr = None

    if os.path.exists("pgnum.png"):
        os.remove("pgnum.png")
    return page_count_ocr, page_count_px


def get_judge_position_ocr(im):
    # crop position from page 1
    first_page = get_nth_page(im, 1)
    title_coords_pg1 = (190, 196, 215, 215)
    first_page.crop(title_coords_pg1).save("position.png")
    # OCR cropped image
    content = str(textract.process("position.png")).strip()

    if os.path.exists("position.png"):
        os.remove("position.png")
    return content


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


def download_new_disclosures(options):
    new_disclosures = FD()
    new_disclosures.iterate_over_aws()


def convert_images(options):
    pattern = os.path.join(
        settings.MEDIA_ROOT, "financial-disclosures/**/*.tiff"
    )
    for filepath in glob.iglob(pattern):
        multipage_basename = re.split(
            r"_Page_\d+.tiff$", filepath, flags=re.IGNORECASE
        )[0]

        if multipage_basename.endswith(".tiff"):
            outpath = "%s.pdf" % os.path.splitext(filepath)[0]
            if os.path.exists(outpath):
                logger.info("Already converted: %s", outpath)
                continue

            logger.info("Converting: %s", outpath)
            fullimage = Image.open(filepath)
            width, height = fullimage.size
            page_count = height / options["page_height"]

            for i in range(page_count):
                im = fullimage.crop(
                    (
                        0,
                        options["page_height"] * i,
                        width,
                        options["page_height"] * (i + 1),
                    )
                )
                if i == 0:
                    im.save(outpath)
                    continue
                pdfpagepath = "%s_im.pdf" % os.path.splitext(filepath)[0]
                im.save(pdfpagepath)
                append_pdfs(outpath, pdfpagepath)
        else:
            outpath = "%s.pdf" % multipage_basename
            if os.path.exists(outpath):
                logger.info("Already converted: %s", outpath)
                continue

            logger.info("Converting: %s", outpath)
            multipage_paths = glob.glob("%s*.tiff" % multipage_basename)
            for i, pg in enumerate(multipage_paths):
                im = Image.open(pg)
                if i == 0:
                    im.save(outpath)
                    continue
                pdfpagepath = "%s_im.pdf" % os.path.splitext(filepath)[0]
                im.save(pdfpagepath)
                append_pdfs(outpath, pdfpagepath)

    if os.path.exists(pdfpagepath):
        os.remove(pdfpagepath)


def append_pdfs(filepath, filepath_appendpdf):
    merger = PdfFileMerger()
    merger.append(PdfFileReader(file(filepath, "rb")))
    merger.append(PdfFileReader(file(filepath_appendpdf, "rb")))
    merger.write(filepath)


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
        # # Action-specific parameters
        # parser.add_argument(
        #     "--case",
        #     help="A case that you want to download when using the add-case "
        #     "action. For example, '19STCV25157;SS;CV'",
        # )
        # parser.add_argument(
        #     "--directory-glob",
        #     help="A directory glob to use when importing bulk JSON files, for "
        #     "example, '/home/you/bulk-data/*.json'. Note that to avoid "
        #     "the shell interpreting the glob, you'll want to put it in "
        #     "single quotes.",
        # )
        # parser.add_argument(
        #     "--skip-until",
        #     type=str,
        #     help="When using --directory-glob, skip processing until an item "
        #     "at this location is encountered. Use a path comparable to "
        #     "that passed to --directory-glob.",
        # )
        # parser.add_argument(
        #     "--reporter",
        #     help="Reporter abbreviation as saved on IA.",
        #     required=False,
        # )

        # parser.add_argument(
        #     "--make-searchable",
        #     action="store_true",
        #     help="Add items to solr as we create opinions. "
        #     "Items are not searchable unless flag is raised.",
        # )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options["action"](options)

    VALID_ACTIONS = {
        "download-files": download_new_disclosures,
        "upload-pdfs": upload_pdfs,
    }
