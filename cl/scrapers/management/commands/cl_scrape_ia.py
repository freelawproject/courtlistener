# !/usr/bin/python
# -*- coding: utf-8 -*-

import os
import json
import argparse
import requests
from internetarchive import get_files, search_items
from cl.lib.command_utils import VerboseCommand, logger
from django.conf import settings

def download_from_internet_archive(options):
    """
    Download cases from internet archive via case law and add write them to
    disk.

    Requires a reporter abbreviation to identify cases to download.

    Opitionally pass in a volume number to download that volume only.  If no
    Volume number provided the code will cycle through the entire reporter
    collection on IA.

    :param options:
    :return:
    """
    reporter = options['reporter']
    reporter_key = ".".join(['law.free.cap',
                       reporter.lower().replace(" ", "-").replace(".", "")])
    volume = options['volume']

    for item in search_items(reporter_key):
        ia_key = item['identifier']
        ia_volume = ia_key.split(".")[-1]

        if volume is not None:
            if volume != ia_volume:
                continue

        for item in get_files(ia_key):
            if "json.json" not in item.name and "json" in item.name:
                url = "https://archive.org/download/%s/%s" % (ia_key, item.name)
                cite = " ".join([ia_volume, reporter, item.name.split(".")[0]])
                file_path = os.path.join(settings.MEDIA_ROOT,
                                         'opinion',
                                         '%s' % url.split("/")[-2],
                                         '%s' % url.split("/")[-1],
                )
                directory = file_path.rsplit("/", 1)[0]
                if os.path.exists(file_path):
                    logger.info("Already captured: %s", cite)
                    continue
                logger.info("Capturing %s:, %s", cite, url)
                if not os.path.exists(directory):
                    os.makedirs(directory)
                with open(file_path, 'w') as outfile:
                    json.dump(requests.get(url).json(), outfile)

class Command(VerboseCommand):
    help = "Parse Tax Cases and import opinions from IA."

    def valid_actions(self, s):
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s" % (
                    ', '.join(self.VALID_ACTIONS.keys())
                )
            )

        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s" % (
                ', '.join(self.VALID_ACTIONS.keys())
            )
        )
        parser.add_argument(
            '--volume',
            help="Volume number. If left blank code will cycle through all "
                 "volumes on Internet Archive.",
        )
        parser.add_argument(
            '--reporter',
            help="Reporter Abbreviation.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        options['action'](options)

    VALID_ACTIONS = {
        'download-from-ia': download_from_internet_archive,
    }
