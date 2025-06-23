"""
How to run it:
docker exec -it cl-django python /opt/courtlistener/manage.py cl_import_dataset_opinions --json-file /opt/courtlistener/cl/assets/media/nhd_metadata.json --court-id nhd

Expected json format:

[
  {
    "citations": "2018 DNH 209",
    "docket_numbers": "18-cv-145-PB",
    "case_names": "Ryan Joseph Swain v. Nancy A. Berryhill, Acting Commissioner, Social Security Administration",
    "case_dates": "2018-10-29",
    "download_urls": "https://www.nhd.uscourts.gov/sites/default/files/Opinions/18/18NH209.pdf",
    "precedential_statuses": "Published",
    "blocked_statuses": false,
    "date_filed_is_approximate": false,
    "case_name_shorts": ""
  },
  {
    "citations": "2018 DNH 136",
    "docket_numbers": "16-cv-33-PB",
    "case_names": "Frank Staples v. NH State Prison Warden, et al.",
    "case_dates": "2018-07-03",
    "download_urls": "https://www.nhd.uscourts.gov/sites/default/files/Opinions/18/18NH136.pdf",
    "precedential_statuses": "Published",
    "blocked_statuses": false,
    "date_filed_is_approximate": false,
    "case_name_shorts": ""
  }
 ]

"""

import io
import json
import logging
import os
import time

import requests
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils.dateparse import parse_date

from cl.corpus_importer.utils import add_citations_to_cluster
from cl.opinion_page.forms import BaseCourtUploadForm
from cl.search.models import Court

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import court opinions from a Json file"

    def add_arguments(self, parser):
        parser.add_argument(
            "--json-file", type=str, help="Path to the Json file."
        )
        parser.add_argument(
            "--court-id", type=str, help="CourtListener Court id"
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

    def handle(self, *args, **options):
        json_file_path = options["json_file"]
        court_id = options["court_id"]
        dry_run = options["dry"]
        limit = options["limit"]
        try:
            court = Court.objects.get(pk=court_id)
        except Court.DoesNotExist:
            logger.error(f"Court with ID '{court_id}' does not exist.")
            return

        logger.info(
            f"{'Dry run' if dry_run else 'Live run'} for court ID: {court_id}"
        )

        with open(json_file_path, encoding="utf-8") as f:
            data = json.load(f)

        if limit is not None:
            data = data[:limit]
            logger.info(f"Limiting processing to first {limit} items")

        total = len(data)
        success_count = 0
        failure_count = 0

        for item in data:
            try:
                pdf_url = item.get("download_urls")
                response = requests.get(pdf_url, timeout=30)

                if response.status_code != 200:
                    logger.error(
                        f"Failed to download PDF: {pdf_url} ({response.status_code})"
                    )
                    failure_count += 1
                    continue

                pdf_bytes = io.BytesIO(response.content)
                pdf_name = os.path.basename(pdf_url)
                pdf_file = InMemoryUploadedFile(
                    file=pdf_bytes,
                    field_name="pdf_upload",
                    name=pdf_name,
                    content_type="application/pdf",
                    size=len(response.content),
                    charset=None,
                )

                form_data = {
                    "court_str": str(court_id),
                    "case_title": item.get("case_names"),
                    "docket_number": item.get("docket_numbers"),
                    "publication_date": parse_date(item.get("case_dates")),
                    "download_url": item.get("download_urls"),
                }

                file_data = {"pdf_upload": pdf_file}

                form = BaseCourtUploadForm(
                    data=form_data, files=file_data, pk=court_id
                )

                if form.is_valid():
                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Validated: {item.get('case_names')}"
                        )
                    else:
                        cluster = form.save()
                        if citations := item.get("citations"):
                            add_citations_to_cluster([citations], cluster.pk)

                        # Wait between each processed row to avoid sending to many indexing tasks
                        time.sleep(1)

                        url = reverse(
                            "view_case", args=[cluster.pk, cluster.docket.slug]
                        )
                        logger.info(
                            f"Successfully imported: {item.get('case_names')} here: {url}"
                        )
                    success_count += 1
                else:
                    logger.error(
                        f"Form errors for '{item.get('case_names')}': {form.errors.as_json()}"
                    )
                    failure_count += 1

            except Exception as e:
                logger.exception(
                    f"Unexpected error processing item '{item.get('case_names', 'Unknown')}': {e}"
                )
                failure_count += 1

        logger.info("-" * 60)
        logger.info(f"Total opinions to import: {total}")
        logger.info(f"Total successfully imported: {success_count}")
        logger.info(f"Total failed to import: {failure_count}")
