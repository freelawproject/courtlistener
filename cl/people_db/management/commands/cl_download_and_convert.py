import os
import re
import argparse
import glob
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.utils import mkdir_p
from django.conf import settings

from PyPDF2 import PdfFileMerger, PdfFileReader
from PIL import Image

import boto3
from botocore import UNSIGNED
from botocore.client import Config


def download_new_disclosures(options):
    bucket = "com-courtlistener-storage"
    prefix = "financial-disclosures"

    assetdir = os.path.join(settings.MEDIA_ROOT, prefix)

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))

    # access_key = settings.AWS_ACCESS_KEY_ID
    # secret_key = settings.AWS_SECRET_ACCESS_KEY
    # s3 = boto3.client(
    #     "s3", aws_access_key_id=access_key, aws_secret_access_key=secret_key
    # )

    kwargs = {"Bucket": bucket, "Prefix": prefix}
    # ctr = 0
    resp = s3.list_objects_v2(**kwargs)
    while True:
        for obj in resp["Contents"]:
            # if count == ctr:
            #     break

            # ctr += 1
            key = obj["Key"]

            subdir = os.path.relpath(key, start=prefix).split("/")[0]

            if subdir == "judicial-watch":
                subdir = re.search(r"\d{4}", key).group()

            print(subdir)

            directory = os.path.join(assetdir, subdir)
            file_path = os.path.join(directory, os.path.basename(key))

            if os.path.exists(file_path):
                logger.info("Already captured: %s", file_path)
                continue

            logger.info("Capturing: %s", file_path)
            mkdir_p(directory)

            with open(file_path, "wb") as f:
                s3.download_fileobj(bucket, key, f)
            try:
                kwargs["ContinuationToken"] = resp["NextContinuationToken"]
            except KeyError:
                break


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


def get_judge_info(key):
    year = None
    subdir = os.path.relpath(key, start=prefix).split("/")[0]

    if subdir == "judicial-watch":
        subdir = re.search(r"\d{4}", key).group()


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
        "convert-images": convert_images,
        "upload-pdfs": upload_pdfs,
    }
