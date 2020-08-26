# !/usr/bin/python
# -*- coding: utf-8 -*-

import os
import internetarchive as ia
import json
import requests

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

    logger.info("Creating IA session...")
    access_key = settings.IA_ACCESS_KEY
    secret_key = settings.IA_SECRET_KEY
    ia_session = ia.get_session(
        {"s3": {"access": access_key, "secret": secret_key}}
    )

    reporter_key = ".".join(["law.free.cap", reporter])

    # Checks that the returned reporter is the requested one.
    # Ex. searching for Mich will return both Mich-app. and Mich.
    for ia_identifier in ia_session.search_items(reporter_key):
        logger.info("Got ia identifier: %s" % ia_identifier)
        ia_key = ia_identifier["identifier"]
        if ia_key.split(".")[3] != reporter:
            continue

        # Checks if we requested a specific volume of the
        # reporter and if so skips all other volumes of that reporter
        ia_volume = ia_key.split(".")[-1]
        if volume is not None:
            if volume != ia_volume:
                continue

        ia_item = ia_session.get_item(ia_key)
        for item in ia_item.get_files():
            logger.info("Got item with name: %s" % item.name)
            if "json.json" in item.name:
                continue

            if "json" not in item.name:
                continue

            url = "https://archive.org/download/%s/%s" % (ia_key, item.name)
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
