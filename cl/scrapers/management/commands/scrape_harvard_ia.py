# !/usr/bin/python
# -*- coding: utf-8 -*-

import os
import json
import requests
from internetarchive import get_files, search_items

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.utils import mkdir_p

from django.conf import settings


def get_from_ia(reporter, volume):
    """
    Download cases from internet archive via case law and write them to
    disk.

    :param reporter: (str) Requires a reporter abbreviation to identify
    cases to download as used by IA.  (Ex. T.C. => tc)
    :param volume: (int) Specific volume number of the reporter.  If blank
    function will cycle through all volumes of the reporter on IA.
    :return: None
    """

    reporter_key = ".".join(["law.free.cap", reporter])

    # Checks that the returned reporter is the requested one.
    # Ex. searching for Mich will return both Mich-app. and Mich.
    for ia_identifier in search_items(reporter_key):
        ia_key = ia_identifier["identifier"]
        if ia_key.split(".")[3] != reporter:
            continue

        # Checks if we requested a specific volume of the
        # reporter and if so skips all other volumes of that reporter
        ia_volume = ia_key.split(".")[-1]
        if volume is not None:
            if volume != ia_volume:
                continue

        for item in get_files(ia_key):
            if "json.json" in item.name:
                continue

            if "json" in item.name:
                url = "https://archive.org/download/%s/%s" % (
                    ia_key,
                    item.name,
                )
                file_path = os.path.join(
                    settings.MEDIA_ROOT,
                    "harvard_corpus",
                    "%s" % ia_key,
                    "%s" % item.name,
                )
                directory = file_path.rsplit("/", 1)[0]
                if os.path.exists(file_path):
                    logger.info("Already captured: %s", url)
                    continue

                logger.info("Capturing: %s", url)
                mkdir_p(directory)
                data = requests.get(url, timeout=10).json()
                with open(file_path, "w") as outfile:
                    json.dump(data, outfile, indent=2)


class Command(VerboseCommand):
    help = "Download and save Harvard corpus on IA to disk."

    def add_arguments(self, parser):
        parser.add_argument(
            "--volume",
            help="Volume number. If none provided, code will cycle through "
            "all volumes of reporter on IA.",
        )
        parser.add_argument(
            "--reporter",
            help="Reporter abbreviation as saved on IA.",
            required=True,
        )

    def handle(self, *args, **options):
        reporter = options["reporter"]
        volume = options["volume"]
        get_from_ia(reporter, volume)
