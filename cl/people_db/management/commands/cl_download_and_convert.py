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
from PyPDF2 import PdfFileMerger, PdfFileReader, PdfFileWriter
from PIL import Image
from cl.scrapers.tasks import extract_by_ocr

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
        self.judge_info = []

    def sorted_list_of_images(self, download_list):
        key_pat = re.compile(r"(.*Page_)(.*)(\.tif)")

        def key(item):
            m = key_pat.match(item)
            return int(m.group(2))

        self.download_urls.sort(key=key)

        xlist = []
        for link in self.download_urls:
            img = Image.open(requests.get(link, stream=True).raw)
            xlist.append(img)
        self.assemble_pdf(xlist, download_list)

    def grab_and_split_image(self, download_list):
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
        self.assemble_pdf(xlist, download_list)

    def assemble_pdf(self, xlist, download_list):
        filename = os.path.basename(download_list[-1]) + ".pdf"
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

        self.judge_info.append(
            {
                "fullname": fullname,
                "title": title,
                "court": court,
                "location": location,
            }
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
        download_list = []
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
                    download_list.append(xkey)
                    # cd['type'] = "pdf"
                    # cd['urls'] = download_urls

                elif "Page_" in key:
                    # Older Pre-split TIFFs
                    if key.split("Page")[0] in download_list:
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
                    download_list.append(xkey)
                else:
                    # Regular old Large TIFF
                    xkey = os.path.splitext(key)[0]
                    self.download_urls.append(self.parent_url + quote(key))
                    download_list.append(xkey)

                self.create_pdf(download_list)

                # TODO: grab the judge names, locations
                # TODO: OCR signature page to get a better name
                # TODO: add metadata into the PDF here

                # add_metadata_to_pdf(
                #     infilepath,
                #     outfilepath,
                #     {
                #         "/fullname": fullname,
                #         "/title": title,
                #         "/court": court,
                #         "/loc": location,
                #     },
                # )

                break

            try:
                self.kwargs["ContinuationToken"] = resp[
                    "NextContinuationToken"
                ]
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
    im_pgnumber.save("pgnum.png")
    is_extracted, content = extract_by_ocr("pgnum.png")
    pagination = re.search("Page \d+ of \d+", content, flags=re.IGNORECASE)
    try:
        page_count_ocr = pagination.group().split()[3]
    except IndexError:
        page_count_ocr = None

    if os.path.exists("pgnum.png"):
        os.remove("pgnum.png")
    return page_count_ocr, page_count_px


def get_judge_info_ocr(im, boundary):
    temp_filepath = temp_filepath = os.path.join(
        settings.MEDIA_ROOT, "financial-disclosures", "crop.png"
    )
    infocrop = im.crop(boundary)
    infocrop.save(temp_filepath)
    is_extracted, content = extract_by_ocr(temp_filepath)

    if os.path.exists(temp_filepath):
        os.remove(temp_filepath)
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
    new_disclosures = FD()
    new_disclosures.iterate_over_aws()


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
        "assign-judges": add_judge_to_disclosure,
        "upload-pdfs": upload_pdfs,
    }
