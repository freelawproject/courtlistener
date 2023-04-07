import sys
import time
from typing import Iterable, List, cast

from django.conf import settings
from django.core.management import CommandError, call_command
from django.core.management.base import CommandParser

from cl.citations.tasks import (
    find_citations_and_parentheticals_for_opinion_by_pks,
)
from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand
from cl.lib.types import OptionsType
from cl.search.models import Opinion


class Command(VerboseCommand):
    help = "Parse citations from RECAP documents."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--doc-id",
            type=int,
            nargs="*",
            help="ids of citing documents",
        )
        parser.add_argument(
            "--start-id",
            type=int,
            help="start id for a range of documents (inclusive)",
        )
        parser.add_argument(
            "--end-id",
            type=int,
            help="end id for a range of documents (inclusive)",
        )
        parser.add_argument(
            "--start-db-date",
            type=int,
            help="starting creation date for a range of documents (inclusive) (filters based on when object entered into database)",
        )
        parser.add_argument(
            "--end-db-date",
            type=int,
            help="ending creation date for a range of documents (inclusive) (filters based on when object entered into database)",
        )
        parser.add_argument(
            "--start-date",
            type=int,
            help="starting upload date for a range of documents (inclusive) (filters based on date document uploaded to PACER)",
        )
        parser.add_argument(
            "--end-date",
            type=int,
            help="ending upload date for a range of documents (inclusive) (filters based on date document uploaded to PACER)",
        )
