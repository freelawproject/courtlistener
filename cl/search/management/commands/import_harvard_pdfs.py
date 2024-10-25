import json
import logging
import os
import tempfile
from typing import Any, Dict, Optional, Tuple

import boto3
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from tqdm import tqdm

from cl.lib.storage import HarvardPDFStorage
from cl.search.models import OpinionCluster

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processed_pdfs = set()

    help = """
    Import PDFs from Harvard Case Law Access Project and update CourtListener models.
    Crosswalk files should be generated from the `generate_cap_crosswalks` management command before running.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--reporter",
            type=str,
            help="Specific reporter to process (e.g., 'A.2d')",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Resume processing from the last completed reporter",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the import process without making changes",
        )
        parser.add_argument(
            "--verbose", action="store_true", help="Increase output verbosity"
        )
        parser.add_argument(
            "--crosswalk-dir",
            type=str,
            help="Directory for reading crosswalk files",
            required=True,
        )
        parser.add_argument(
            "--job",
            type=str,
            choices=["import_pdf", "assign_cap_id"],
            default="import_pdf",
            help="",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Handle the command execution.

        :param args: Additional arguments.
        :param options: Command options.
        :return: None
        """
        logger.info("Starting import_harvard_pdfs command")
        if options["verbose"]:
            logger.setLevel(logging.DEBUG)

        self.dry_run = options["dry_run"]
        self.crosswalk_dir = options["crosswalk_dir"]
        self.job = options["job"]

        if not os.path.exists(self.crosswalk_dir):
            logger.warning(
                f"Crosswalk directory does not exist: {self.crosswalk_dir}"
            )
            return

        self.setup_s3_clients()
        self.process_crosswalks(options["reporter"], options["resume"])

    def setup_s3_clients(self) -> None:
        """Initialize S3 client for accessing Harvard CAP R2.

        :return: None
        """
        # Initialize S3 client for accessing Harvard CAP R2
        self.cap_client = boto3.client(
            "s3",
            endpoint_url=settings.CAP_R2_ENDPOINT_URL,
            aws_access_key_id=settings.CAP_R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.CAP_R2_SECRET_ACCESS_KEY,
        )
        self.cap_bucket_name = settings.CAP_R2_BUCKET_NAME

    def process_crosswalks(
        self, specific_reporter: Optional[str], resume: bool
    ) -> None:
        """Process crosswalk files for importing PDFs.

        :param specific_reporter: Specific reporter to process, if any.
        :param resume: Whether to resume from the last completed reporter.
        :return: None
        """
        logger.info(
            f"Processing crosswalks. Reporter: {specific_reporter}, Resume: {resume}"
        )
        last_reporter_file = os.path.join(
            self.crosswalk_dir, "last_completed_reporter.txt"
        )

        # Load the last completed reporter if resuming
        if resume:
            try:
                with open(last_reporter_file, "r") as f:
                    last_completed_reporter = f.read().strip()
                resume = True
            except FileNotFoundError:
                logger.warning(
                    "No last completed reporter file found. Starting from the beginning."
                )
                last_completed_reporter = None
                resume = False
        else:
            last_completed_reporter = None

        for filename in sorted(os.listdir(self.crosswalk_dir)):
            if filename.endswith(".json"):
                reporter = filename.replace("_", ".").rstrip(".json")

                # Skip reporters until we reach the resume point
                if resume and last_completed_reporter:
                    if reporter <= last_completed_reporter:
                        logger.info(
                            f"Skipping already processed reporter: {reporter}"
                        )
                        continue

                if specific_reporter and reporter != specific_reporter:
                    continue

                logger.info(f"Starting to process reporter: {reporter}")
                self.process_crosswalk_file(
                    os.path.join(self.crosswalk_dir, filename)
                )

                # Log the completed reporter
                logger.info(f"Completed processing reporter: {reporter}")
                with open(last_reporter_file, "w") as f:
                    f.write(reporter)

    def process_crosswalk_file(self, crosswalk_file: str) -> None:
        """Process a single crosswalk file.

        :param crosswalk_file: Path to the crosswalk file.
        :return: None
        """
        logger.info(f"Processing crosswalk file: {crosswalk_file}")
        with open(crosswalk_file, "r") as f:
            crosswalk_data = json.load(f)

        for entry in tqdm(crosswalk_data, desc="Processing entries"):
            try:
                cap_case_id = entry["cap_case_id"]
                cl_cluster_id = entry["cl_cluster_id"]
                cap_path = entry["cap_path"]

                if not all([cap_case_id, cl_cluster_id, cap_path]):
                    logger.error(
                        f"Missing key in entry: {json.dumps(entry, indent=2)}"
                    )
                    continue

                logger.debug(
                    f"Processing entry: cap_case_id={cap_case_id}, cl_cluster_id={cl_cluster_id}, cap_path={cap_path}"
                )

                self.process_entry(cap_case_id, cl_cluster_id, cap_path)

            except Exception as e:
                logger.error(
                    f"Error processing CAP ID {entry.get('cap_case_id', 'Unknown')}: {str(e)}",
                    exc_info=True,
                )

    def parse_cap_path(self, cap_path: str) -> Tuple[str, str, str]:
        """Extract data from CAP path.

        :param cap_path: CAP path string.
        :return: Tuple containing reporter_slug, volume_folder, and case_name.
        """
        # Extract data from CAP path
        parts = cap_path.strip("/").split("/")
        reporter_slug = parts[0]
        volume_folder = parts[1]
        case_name = parts[-1].replace(".json", "")
        return reporter_slug, volume_folder, case_name

    def process_entry(
        self, cap_case_id: int, cl_cluster_id: int, cap_path: str
    ) -> None:
        """Process a single crosswalk entry.

        :param cap_case_id: CAP case id
        :param cl_cluster_id: CL cluster id
        :param cap_path: Path of CAP JSON data (in the CAP_R2 S3 bucket)
        :return: None
        """

        match self.job:
            case "import_pdf":
                try:
                    pdf_path = cap_path.replace("cases", "case-pdfs").replace(
                        ".json", ".pdf"
                    )

                    if pdf_path in self.processed_pdfs:
                        logger.info(
                            f"Skipping already processed PDF: {pdf_path}"
                        )
                        return

                    logger.info(f"Processing PDF: {pdf_path}")

                    if not self.dry_run:
                        pdf_content = self.fetch_pdf_from_cap(pdf_path)
                        if pdf_content:
                            cluster = OpinionCluster.objects.get(
                                id=cl_cluster_id
                            )
                            self.store_pdf_in_cl(cluster, pdf_content)
                    else:
                        logger.info(
                            f"Dry run: Would fetch PDF from {pdf_path}"
                        )

                    self.processed_pdfs.add(pdf_path)

                except OpinionCluster.DoesNotExist:
                    logger.info(f"Cluster not found for id: {cl_cluster_id}")

            case "assign_cap_id":
                try:
                    cluster = OpinionCluster.objects.get(id=cl_cluster_id)
                    cluster.harvard_id = cap_case_id
                    if not self.dry_run:
                        cluster.save()

                except OpinionCluster.DoesNotExist:
                    logger.info(f"Cluster not found for id: {cl_cluster_id}")

            case _:
                raise Exception(f"Unknown job {self.job}")

    def fetch_pdf_from_cap(self, pdf_path: str) -> Optional[bytes]:
        """Fetch PDF content from CAP.

        :param pdf_path: Path to the PDF in CAP storage.
        :return: PDF content as bytes, or None if fetching fails.
        """
        logger.info(f"Fetching PDF from CAP: {pdf_path}")
        logger.debug(f"Bucket name: {self.cap_bucket_name}")

        pdf_path = pdf_path.lstrip("/")

        if self.dry_run:
            logger.info(f"Dry run: Would fetch PDF from {pdf_path}")
            return b"Mock PDF content"

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                logger.debug(f"Attempting to download file: {pdf_path}")
                self.cap_client.download_file(
                    self.cap_bucket_name, pdf_path, temp_file.name
                )
                with open(temp_file.name, "rb") as f:
                    pdf_content = f.read()
                logger.debug(
                    f"Downloaded PDF to temporary file: {temp_file.name}"
                )
                logger.debug(f"Read PDF content, length: {len(pdf_content)}")
                return pdf_content
        except Exception as e:
            logger.error(
                f"Error fetching PDF from CAP: {str(e)}", exc_info=True
            )
            return None
        finally:
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)

    def store_pdf_in_cl(
        self, cluster: OpinionCluster, pdf_content: bytes
    ) -> None:
        """Store the fetched PDF in CourtListener's storage.

        :param cluster: OpinionCluster object to associate the PDF with.
        :param pdf_content: PDF content as bytes.
        :return: None
        """
        logger.info(f"Storing PDF for cluster: {cluster.id}")
        storage = HarvardPDFStorage()
        file_path = f"harvard_pdf/{cluster.pk}.pdf"
        logger.debug(f"Saving file to: {file_path}")

        try:
            content_file = ContentFile(pdf_content)

            saved_path = storage.save(file_path, content_file)
            logger.info(f"File saved successfully at: {saved_path}")

            cluster.filepath_pdf_harvard = saved_path
            cluster.save()
            logger.info(
                f"Cluster updated. filepath_pdf_harvard: {cluster.filepath_pdf_harvard}"
            )
        except Exception as e:
            logger.error(
                f"Error saving PDF for cluster {cluster.id}: {str(e)}",
                exc_info=True,
            )


if __name__ == "__main__":
    import sys

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
