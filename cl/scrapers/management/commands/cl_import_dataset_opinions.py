import argparse
import json
import os
import signal
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

import requests
from django.utils.encoding import force_bytes
from juriscraper.lib.exceptions import InvalidDocumentError
from juriscraper.lib.string_utils import CaseNameTweaker
from sentry_sdk import capture_exception

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.crypto import sha1
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.exceptions import (
    BadContentError,
    ConsecutiveDuplicatesError,
    EmptyFileError,
    SingleDuplicateError,
)
from cl.scrapers.management.commands.cl_scrape_opinions import (
    make_objects,
    save_everything,
)
from cl.scrapers.tasks import extract_doc_content
from cl.scrapers.utils import (
    get_child_court,
    signal_handler,
)
from cl.search.models import (
    Court,
    Opinion,
)

# For use in catching the SIGINT (Ctrl+4)
die_now = False
cnt = CaseNameTweaker()


class Command(VerboseCommand):
    help = "Runs the Juriscraper data stored locally to import opinions"

    def read_binary_from_url(self, url):
        """Reads the binary content from a URL

        :param url: The URL of the file.
        :return: The binary content of the file as bytes, or None if an error occurs.
        """
        response = requests.get(url, stream=True)
        if len(response.content) == 0:
            raise EmptyFileError(f"The downloaded file from {url} is empty")
        # Raise an exception for bad status codes
        response.raise_for_status()
        # TODO content = site.cleanup_content(r.content) ??
        return response.content

    def ingest_a_case(
        self,
        item: dict,
        next_case_date: date | None,
        ocr_available: bool,
        juriscraper_module: str,
        dup_checker: DupChecker,
        court: Court,
    ):
        """Ingest a new case

        :param item: data obtained from juriscraper scraper
        :param next_case_date:
        :param ocr_available:
        :param juriscraper_module:
        :param dup_checker:
        :param dupcourt_checker:
        :return:
        """

        content = self.read_binary_from_url(item["s3_url"])

        # request.content is sometimes a str, sometimes unicode, so
        # force it all to be bytes, pleasing hashlib.
        sha1_hash = sha1(force_bytes(content))

        lookup_params = {
            "lookup_value": sha1_hash,
            "lookup_by": "sha1",
        }

        # Duplicates will raise errors
        dup_checker.press_on(
            Opinion, item["case_dates"], next_case_date, **lookup_params
        )

        # Not a duplicate, carry on
        logger.info(
            "Adding new document found at: %s", item["s3_url"].encode()
        )
        dup_checker.reset()

        child_court = get_child_court(item.get("child_courts", ""), court.id)

        docket, opinion, cluster, citations = make_objects(
            item, child_court or court, sha1_hash, content
        )

        save_everything(
            items={
                "docket": docket,
                "opinion": opinion,
                "cluster": cluster,
                "citations": citations,
            }
        )

        extract_doc_content.delay(
            opinion.pk,
            ocr_available=ocr_available,
            citation_jitter=True,
            juriscraper_module=juriscraper_module,
        )

        logger.info(
            "Successfully added opinion %s: %s",
            opinion.pk,
            item["case_names"].encode(),
        )

    def parse_metadata(self, file_path: str, ocr_available: bool = True):
        """Reads the json file and apply neccesary transformation for dates

        :param file_path: path to json file
        :param ocr_available:
        :return None
        """

        def date_hook(json_dict):
            """Decode json object to convert date string values to
            datetime.date objects

            :param json_dict: json object
            :return updated json object
            """
            for key, value in json_dict.items():
                if isinstance(value, str):
                    try:
                        json_dict[key] = datetime.fromisoformat(value).date()
                    except ValueError:
                        pass
            return json_dict

        with open(file_path) as f:
            logger.info("Processing file: %s", file_path)

            loaded_data = json.load(f, object_hook=date_hook)

            if not isinstance(loaded_data, list):
                raise ValueError(
                    f"Expected JSON array, got {type(loaded_data).__name__}"
                )

            if not loaded_data:
                raise ValueError("JSON array is empty")

            # Get court id from first element
            court_id = loaded_data[0].get("court_pk")
            juriscraper_module = loaded_data[0].get("juriscraper_module")

            court = Court.objects.get(pk=court_id)

            dup_checker = DupChecker(court)

            # filepath_hash = hashlib.sha1(file_path.encode()).hexdigest()
            # TODO use hash generate from filepath to avoid rerun the file?
            # if dup_checker.abort_by_url_hash(file_path, filepath_hash):
            #     logger.debug("Aborting by file hash.")
            #     return

            logger.debug("#%s opinion found.", len(loaded_data))

            added = 0

            for i, item in enumerate(loaded_data):
                # logger.info(f"processing {item}")

                try:
                    next_date = loaded_data[i + 1]["case_dates"]
                except IndexError:
                    next_date = None

                try:
                    self.ingest_a_case(
                        item,
                        next_date,
                        ocr_available,
                        juriscraper_module,
                        dup_checker,
                        court,
                    )
                    added += 1
                except ConsecutiveDuplicatesError:
                    break
                except (
                    SingleDuplicateError,
                    BadContentError,
                    InvalidDocumentError,
                ):
                    pass

            logger.debug(
                "%s: Successfully crawled %s/%s opinions.",
                court_id,
                added,
                len(loaded_data),
            )

            # Update the hash if everything finishes properly.
            # if not full_crawl:
            #     # Only update the hash if no errors occurred.
            #     dup_checker.update_site_hash(site.hash)

    @staticmethod
    def validate_json_file(path: str):
        """Custom validator for --json-file command line argument

        :param path: File path to validate
        :return: validated file path
        """
        if not path.lower().endswith(".json"):
            raise argparse.ArgumentTypeError("File must have .json extension")
        if not os.path.isfile(path):
            raise argparse.ArgumentTypeError(f"File not found: {path}")
        return path

    @staticmethod
    def validate_json_dir(path: str):
        """Custom validator for --json-dir command line argument

        :param path: directory path with json files
        :return: validated directory path
        """
        if not os.path.isdir(path):
            raise argparse.ArgumentTypeError(f"Directory not found: {path}")
        if not any(Path(path).glob("*.json")):
            raise argparse.ArgumentTypeError(
                f"No .json files found in directory: {path}"
            )
        return path

    def add_arguments(self, parser):
        super().add_arguments(parser)
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--json-file",
            type=self.validate_json_file,
            help="Path to JSON file",
        )
        group.add_argument(
            "--json-dir",
            type=self.validate_json_dir,
            help="Path to directory containing .json files",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        global die_now
        files = []

        # this line is used for handling SIGTERM (CTRL+4), so things can die
        # safely
        signal.signal(signal.SIGTERM, signal_handler)

        files = []

        if options["json_file"]:
            files.append(options["json_file"])

        if options["json_dir"]:
            files.extend(
                str(f) for f in Path(options["json_dir"]).glob("*.json")
            )

        logger.info("Starting up process.")
        num_files = len(files)
        logger.info("Files found: %s", num_files)

        for i, file_path in enumerate(files):
            # this catches SIGTERM, so the code can be killed safely.
            if die_now:
                logger.info("The scraper has stopped.")
                sys.exit(1)

            try:
                self.parse_metadata(file_path)
            except Exception as e:
                capture_exception(e, fingerprint=[file_path, "{{ default }}"])
                logger.debug(traceback.format_exc())

        logger.info("The scraper has stopped.")
