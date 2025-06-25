"""
How to run it:
docker exec -it cl-django python /opt/courtlistener/manage.py cl_import_dataset_opinions --files-dir /opt/courtlistener/cl/assets/media/nhd --court-id juriscraper.opinions.united_states.federal_appellate.ca1

Expected json format:

{
  "citations": "2017 DNH 158",
  "docket_numbers": "16-cv-522-PB",
  "case_names": "Pitroff v USA",
  "case_dates": "2017-08-22",
  "download_urls": "https://www.nhd.uscourts.gov/sites/default/files/Opinions/17/17NH158.pdf",
  "precedential_statuses": "Published",
  "blocked_statuses": false,
  "date_filed_is_approximate": false,
  "case_name_shorts": "Pitroff v USA",
  "url_hash": "0a04dfe649d8a3a9a65b879e90d5ef577d49d70b"
}

"""

import json
import logging
from json import JSONDecodeError
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.encoding import force_bytes
from juriscraper.lib.importer import build_module_list

from cl.lib.crypto import sha1
from cl.scrapers.DupChecker import DupChecker
from cl.scrapers.exceptions import (
    ConsecutiveDuplicatesError,
    SingleDuplicateError,
)
from cl.scrapers.management.commands.cl_scrape_opinions import (
    make_objects,
    save_everything,
)
from cl.scrapers.tasks import extract_doc_content
from cl.scrapers.utils import get_child_court
from cl.search.models import Court, Opinion

logger = logging.getLogger(__name__)

VALID_EXTENSIONS = [".pdf", ".doc", ".docx", ".wpd", ".txt", ".html"]


class Command(BaseCommand):
    help = "Import court opinions from a Json file"

    @staticmethod
    def validate_files_dir(path: str) -> Path:
        """Ensure the directory exists and is readable.

        :param path: path to directory
        :return directory path
        """
        dir_path = Path(path)
        if not dir_path.exists():
            raise CommandError(f"Provided path '{path}' does not exist.")
        if not dir_path.is_dir():
            raise CommandError(f"Provided path '{path}' is not a directory.")
        return dir_path

    @staticmethod
    def find_opinion_file(files_dir: Path, url_hash: str) -> Path | None:
        for ext in VALID_EXTENSIONS:
            candidate = files_dir / f"{url_hash}{ext}"
            if candidate.exists():
                return candidate
        return None

    def add_arguments(self, parser):
        parser.add_argument(
            "--files-dir",
            type=self.validate_files_dir,
            required=True,
            help="Directory containing JSON files and opinion files.",
        )
        parser.add_argument(
            "--court-id",
            type=str,
            required=True,
            help="CourtListener juriscraper module, e.g. juriscraper.opinions.united_states.federal_appellate.ca1",
        )
        parser.add_argument(
            "--dry",
            action="store_true",
            help="Run in dry mode (do not save anything to the database).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of items to process from the Json file.",
        )
        parser.add_argument(
            "--start-from",
            type=str,
            help="Filename (e.g. 0a03...json) to start processing from (inclusive).",
        )

    def handle(self, *args, **options):
        files_dir = Path(options["files_dir"])
        court_id = options["court_id"]
        dry_run = options["dry"]
        limit = options["limit"]

        module_strings = build_module_list(court_id)
        package, module = module_strings[0].rsplit(".", 1)

        mod = __import__(f"{package}.{module}", globals(), locals(), [module])
        module_string = mod.Site().court_id
        court_id = module_string.split(".")[-1].split("_")[0]

        try:
            court = Court.objects.get(pk=court_id)
        except Court.DoesNotExist:
            logger.error(f"Court with ID '{court_id}' does not exist.")
            return

        json_files = sorted(files_dir.glob("*.json"))
        json_filenames = [file.name for file in json_files]

        start_from = options.get("start_from")
        if start_from:
            if start_from not in json_filenames:
                raise CommandError(
                    f"Start file '{start_from}' not found in directory."
                )
            start_index = json_filenames.index(start_from)
            json_files = json_files[start_index:]
            logger.info(f"Starting import from file: {start_from}")

        if limit:
            json_files = json_files[:limit]
            logger.info(
                f"Limiting to first {limit} JSON files after start point"
            )

        logger.info(
            f"{'Dry run' if dry_run else 'Live run'} for court ID: {court_id}"
        )

        for json_path in json_files:
            try:
                with json_path.open("r", encoding="utf-8") as f:
                    item = json.load(f)
                    item["case_dates"] = parse_date(item.get("case_dates"))

                url_hash = item.get("url_hash")
                if not url_hash:
                    logger.warning(
                        f"No 'url_hash' found in {json_path.name}, skipping."
                    )
                    continue

                opinion_path = self.find_opinion_file(files_dir, url_hash)

                if not opinion_path:
                    logger.error(
                        f"No matching opinion file found for hash {url_hash} in {json_path.name}"
                    )
                    continue

                with opinion_path.open("rb") as file:
                    content = file.read()

                sha1_hash = sha1(force_bytes(content))

                lookup_params = {
                    "lookup_value": sha1_hash,
                    "lookup_by": "sha1",
                }

                dup_checker = DupChecker(court, full_crawl=True)

                try:
                    dup_checker.press_on(
                        Opinion, item["case_dates"], None, **lookup_params
                    )
                except ConsecutiveDuplicatesError:
                    break
                except SingleDuplicateError:
                    continue

                child_court = get_child_court(
                    item.get("child_courts", ""), court.id
                )
                docket, opinion, cluster, citations = make_objects(
                    item, child_court or court, sha1_hash, content
                )

                if dry_run:
                    logger.info(
                        f"[DRY RUN] Validated: {item.get('case_names')}"
                    )
                else:
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
                        ocr_available=True,
                        citation_jitter=True,
                        juriscraper_module=module_string,
                    )

                    url = reverse(
                        "view_case", args=[cluster.pk, cluster.docket.slug]
                    )
                    logger.info(
                        f"Successfully imported: {item.get('case_names')} here: {url}"
                    )

            except JSONDecodeError as e:
                logger.error(f"Invalid JSON in {json_path.name}: {e}")
                continue
