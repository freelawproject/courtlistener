import os
import json
import boto3
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files.base import ContentFile
from cl.search.models import OpinionCluster
from cl.lib.storage import IncrementingAWSMediaStorage
from tqdm import tqdm
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import PDFs from Harvard Case Law Access Project and update CourtListener models"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cl_storage = IncrementingAWSMediaStorage()

    def add_arguments(self, parser):
        parser.add_argument(
            "--reporter",
            type=str,
            help="Specific reporter to process (e.g., 'A.2d')",
        )
        parser.add_argument(
            "--resume-from",
            type=str,
            help="Resume processing from this CAP ID",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the import process without making changes",
        )
        parser.add_argument(
            "--verbose", action="store_true", help="Increase output verbosity"
        )

    def handle(self, *args, **options):
        if options["verbose"]:
            logger.setLevel(logging.DEBUG)

        self.dry_run = options["dry_run"]
        self.setup_s3_clients()
        self.process_crosswalks(options["reporter"], options["resume_from"])

    def setup_s3_clients(self):
        self.cap_client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        )
        self.cap_bucket_name = settings.R2_BUCKET_NAME
        self.cl_storage = IncrementingAWSMediaStorage()

    def process_crosswalks(self, specific_reporter, resume_from):
        # Use a relative path to the crosswalks directory
        crosswalk_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "crosswalks",
        )
        for filename in os.listdir(crosswalk_dir):
            if filename.endswith(".json"):
                reporter = filename.replace("_", ".").rstrip(".json")
                if specific_reporter and reporter != specific_reporter:
                    continue
                self.process_crosswalk_file(
                    os.path.join(crosswalk_dir, filename), resume_from
                )

    def process_crosswalk_file(self, crosswalk_file, resume_from):
        logger.info(f"Processing crosswalk file: {crosswalk_file}")
        with open(crosswalk_file, "r") as f:
            crosswalk_data = json.load(f)

        resume_index = 0
        if resume_from:
            resume_index = next(
                (
                    i
                    for i, entry in enumerate(crosswalk_data)
                    if entry["cap_id"] == int(resume_from)
                ),
                0,
            )

        for entry in tqdm(
            crosswalk_data[resume_index:], desc="Processing entries"
        ):
            self.process_entry(entry)

    def process_entry(self, entry):
        cap_id = entry["cap_id"]
        cl_id = entry["cl_id"]
        cap_path = entry["cap_path"]

        logger.debug(f"Processing entry: CAP ID {cap_id}, CL ID {cl_id}")

        try:
            cluster = OpinionCluster.objects.get(id=cl_id)
        except OpinionCluster.DoesNotExist:
            logger.warning(f"OpinionCluster with id {cl_id} not found")
            return

        pdf_content = self.fetch_pdf_from_cap(cap_path)
        if pdf_content:
            self.store_pdf_in_cl(cluster, pdf_content)

    def fetch_pdf_from_cap(self, cap_path):
        pdf_path = cap_path.replace("/cases/", "/pdf/").replace(
            ".json", ".pdf"
        )
        logger.debug(f"Fetching PDF from CAP: {pdf_path}")

        if self.dry_run:
            logger.info(f"Dry run: Would fetch PDF from {pdf_path}")
            return b"Mock PDF content"

        try:
            response = self.cap_client.get_object(
                Bucket=self.cap_bucket_name, Key=pdf_path
            )
            return response["Body"].read()
        except Exception as e:
            logger.error(f"Error fetching PDF from CAP: {str(e)}")
            return None

    def store_pdf_in_cl(self, cluster, pdf_content):
        file_name = f"harvard_pdf/{cluster.pk}.pdf"
        logger.debug(f"Storing PDF for cluster {cluster.pk}")

        if self.dry_run:
            logger.info(f"Dry run: Would store PDF for cluster {cluster.pk}")
            return

        try:
            content_file = ContentFile(pdf_content)
            stored_name = self.cl_storage.save(file_name, content_file)

            cluster.filepath_pdf_harvard = stored_name
            cluster.save()

            logger.info(f"Stored PDF for cluster {cluster.pk}")
        except Exception as e:
            logger.error(
                f"Error storing PDF for cluster {cluster.pk}: {str(e)}"
            )


if __name__ == "__main__":
    from django.core.management import execute_from_command_line
    import sys

    execute_from_command_line(sys.argv)
