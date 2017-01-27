import argparse
import glob
import logging
import os
import random

from django.conf import settings
from django.core.management import BaseCommand
from lxml import etree

from cl.lib.pacer import PacerXMLParser

logger = logging.getLogger(__name__)


def get_docket_list(path=None):
    """Get a list of files from the recap directory and prep it for
    iteration.
    """
    if not path:
        path = os.path.join(settings.MEDIA_ROOT, 'recap', '*.xml')
    else:
        path = os.path.join(path, '*.xml')
    return sorted(glob.glob(path))


class Command(BaseCommand):
    help = ('Go through every item downloaded from RECAP, parse it, and add it '
            'to the database.')

    def valid_actions(self, s):
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s" % (
                    ', '.join(self.VALID_ACTIONS.keys())
                )
            )

        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser):
        # Global args.
        parser.add_argument(
            '--action',
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s" % (
                ', '.join(self.VALID_ACTIONS.keys())
            )
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            default=False,
            help="Don't change the data."
        )

        # Parsing
        parser.add_argument(
            '--start_item',
            type=int,
            default=0,
            help='The line in the file where you wish to start processing.'
        )
        parser.add_argument(
            '--max_items',
            type=int,
            default=-1,
            help="The maximum number of items to parse. -1 indicates all items "
                 "should be parsed."
        )

        # Data sampling
        parser.add_argument(
            '--xpath',
            help="The xpath that you wish to sample",
        )
        parser.add_argument(
            '--sample_size',
            type=int,
            default=1000,
            help="The number of items to sample",
        )
        parser.add_argument(
            '--path',
            help="The path where docket XML files can be found.",
        )

    def handle(self, *args, **options):
        self.debug = options['debug']
        self.options = options

        # Run the requested method.
        self.options['action'](self)

    def sample_dockets(self):
        """Iterate over `node_count` items and extract the value at the XPath.

        If there are not `node_count` recap dockets on disk, do the lesser of
        the two.
        """
        docket_paths = get_docket_list(self.options['path'])
        random.shuffle(docket_paths)

        completed = 0
        no_value = 0
        for docket_path in docket_paths:
            with open(docket_path, 'r') as f:
                docket_xml_content = f.read()

                if not docket_xml_content:
                    continue

            # Extract the xpath value
            tree = etree.fromstring(docket_xml_content)
            value = tree.xpath(self.options['xpath'])

            if value:
                print "%s: %s" % (completed, value)
                completed += 1
            else:
                no_value += 1

            if completed == self.options['sample_size']:
                break

        print '\n%s items had no value.' % no_value

    def parse_items(self):
        """For every item in the directory, send it to Celery for processing"""
        docket_paths = get_docket_list()

        completed = 0
        for docket_path in docket_paths:
            if completed < self.options['start_item'] - 1:
                # Skip ahead if start_lines is provided.
                completed += 1
                continue
            else:
                logger.info("%s: Parsing docket: %s" % (completed, docket_path))

                pacer_doc = PacerXMLParser(docket_path)

                docket = pacer_doc.save(self.debug)
                if docket is not None:
                    pacer_doc.make_documents(docket, self.debug)

                completed += 1

                max_items = self.options['max_items']
                if completed >= max_items != -1:
                    print "\n\nCompleted %s items. Aborting early." % max_items
                    break

    VALID_ACTIONS = {
        'sample-dockets': sample_dockets,
        'parse-dockets': parse_items,
    }
