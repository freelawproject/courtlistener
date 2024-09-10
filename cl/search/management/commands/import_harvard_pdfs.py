import os
import json
import boto3
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from cl.search.models import OpinionCluster
from cl.lib.storage import IncrementingAWSMediaStorage
from tqdm import tqdm
import logging
import tempfile
from storages.backends.s3boto3 import S3Boto3Storage
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


class HarvardPDFStorage(S3Boto3Storage):
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    custom_domain = settings.AWS_S3_CUSTOM_DOMAIN
    default_acl = settings.AWS_DEFAULT_ACL
    querystring_auth = settings.AWS_QUERYSTRING_AUTH
    max_memory_size = settings.AWS_S3_MAX_MEMORY_SIZE


class Command(BaseCommand):
    help = "Import PDFs from Harvard Case Law Access Project and update CourtListener models"

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
        # Set logging level if verbose option is provided
        if options["verbose"]:
            logger.setLevel(logging.DEBUG)

        self.dry_run = options["dry_run"]
        self.setup_s3_clients()
        self.process_crosswalks(options["reporter"], options["resume_from"])

    def setup_s3_clients(self):
        # Initialize S3 client for accessing Harvard CAP R2
        self.cap_client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        )
        self.cap_bucket_name = settings.R2_BUCKET_NAME

    def process_crosswalks(self, specific_reporter, resume_from):
        # Process crosswalk files for mapping between CAP and CL IDs
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

        # Find the index to resume from resuming a run
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
            reporter_slug, volume_folder, case_name = self.parse_cap_path(
                entry["cap_path"]
            )
            entry["reporter_slug"] = reporter_slug
            entry["volume_folder"] = volume_folder
            entry["case_name"] = case_name
            self.process_entry(entry)

    def parse_cap_path(self, cap_path):
        # Extract data from CAP path
        parts = cap_path.strip("/").split("/")
        reporter_slug = parts[0]
        volume_folder = parts[1]
        case_name = parts[-1].replace(".json", "")
        return reporter_slug, volume_folder, case_name

    def process_entry(self, entry):
        cap_id = entry["cap_id"]
        cl_id = entry["cl_id"]
        reporter_slug = entry["reporter_slug"]
        volume_folder = entry["volume_folder"]
        case_name = entry["case_name"]

        logger.debug(f"Processing entry: CAP ID {cap_id}, CL ID {cl_id}")

        try:
            cluster = OpinionCluster.objects.get(id=cl_id)
        except OpinionCluster.DoesNotExist:
            logger.warning(f"OpinionCluster with id {cl_id} not found")
            return

        pdf_path = f"{reporter_slug}/{volume_folder}/case-pdfs/{case_name}.pdf"
        pdf_content = self.fetch_pdf_from_cap(pdf_path)
        if pdf_content and not self.dry_run:
            self.store_pdf_in_cl(cluster, pdf_content)
        elif not pdf_content:
            logger.warning(f"Failed to fetch PDF for cluster {cl_id}")

    def fetch_pdf_from_cap(self, pdf_path):
        logger.debug(f"Fetching PDF from CAP: {pdf_path}")
        logger.debug(f"Bucket name: {self.cap_bucket_name}")

        if self.dry_run:
            logger.info(f"Dry run: Would fetch PDF from {pdf_path}")
            return b"Mock PDF content"

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                self.cap_client.download_file(
                    self.cap_bucket_name, pdf_path, temp_file.name
                )
                with open(temp_file.name, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.error(f"Error fetching PDF from CAP: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            if hasattr(e, "response"):
                logger.error(f"Error response: {e.response}")
            return None
        finally:
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

    def store_pdf_in_cl(self, cluster, pdf_content):
        # Store the fetched PDF in CourtListener's storage
        storage = HarvardPDFStorage()
        file_name = f"harvard_pdf/{cluster.id}.pdf"
        content_file = ContentFile(pdf_content)

        try:
            saved_name = storage.save(file_name, content_file)
            cluster.filepath_pdf_harvard = saved_name
            cluster.save()
            logger.info(f"Stored PDF for cluster {cluster.id} at {saved_name}")
        except (BotoCoreError, ClientError) as e:
            logger.error(
                f"Failed to store PDF for cluster {cluster.id}: {str(e)}"
            )


if __name__ == "__main__":
    from django.core.management import execute_from_command_line
    import sys

    execute_from_command_line(sys.argv)
