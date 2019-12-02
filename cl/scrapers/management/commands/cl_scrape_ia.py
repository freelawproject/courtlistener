# !/usr/bin/python
# -*- coding: utf-8 -*-

import os
import json
import requests
from internetarchive import get_files, search_items

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.utils import mkdir_p

from django.conf import settings

class Command(VerboseCommand):
    help = 'Download and save Harvard corpus on IA to disk.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--volume',
            help="Volume number. If left blank code will cycle through all "
                 "volumes of reporter in IA.",
        )
        parser.add_argument(
            '--reporter',
            help="Reporter abbreviation as used on IA.",
            required=True,
        )

    def handle(self, *args, **options):
        """
        Download cases from internet archive via case law and write them to
        disk.

        Requires a reporter abbreviation to identify cases to download as
        used by IA.  (Ex. T.C. => tc)

        Opitionally pass in a volume number to download that volume only.  If no
        Volume number provided the code will cycle through the entire reporter
        collection on IA.

        :param options:
        :return:
        """
        reporter = options['reporter']
        reporter_key = ".".join(['law.free.cap', reporter])
        volume = options['volume']

        for item in search_items(reporter_key):
            ia_key = item['identifier']
            if ia_key.split(".")[3] != reporter:
                continue

            ia_volume = ia_key.split(".")[-1]
            if volume is not None:
                if volume != ia_volume:
                    continue

            for item in get_files(ia_key):
                if "json.json" in item.name:
                    continue

                if "json" in item.name:
                    url = "https://archive.org/download/%s/%s" % (
                    ia_key, item.name)
                    cite = " ".join(
                        [ia_volume, reporter, item.name.split(".")[0]])
                    file_path = os.path.join(settings.MEDIA_ROOT,
                                             'harvard_corpus',
                                             '%s' % ia_key,
                                             '%s' % item.name,
                                             )
                    directory = file_path.rsplit("/", 1)[0]
                    if os.path.exists(file_path):
                        logger.info("Already captured: %s", cite)
                        continue

                    logger.info("Capturing (%s): %s", cite, url)
                    mkdir_p(directory)
                    with open(file_path, 'w') as outfile:
                        json.dump(requests.get(url).json(), outfile, indent=2)
