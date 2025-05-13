import json
import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import boto3
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

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
            "--start-from-reporter",
            type=str,
            help="Process starting from this reporter (e.g., 'A.2d')",
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
            "--max-workers",
            type=int,
            default=2,
            help="The maximum number of concurrent processes to use.",
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
        self.resume = options["resume"]
        self.reporter = options["reporter"]
        self.crosswalk_dir = options["crosswalk_dir"]
        self.max_workers = options["max_workers"]
        self.start_from_reporter = options["start_from_reporter"]

        if not os.path.exists(self.crosswalk_dir):
            logger.warning(
                "Crosswalk directory does not exist: %s", self.crosswalk_dir
            )
            return

        if self.resume and self.start_from_reporter:
            logger.warning(
                "You can't combine --resume and --start-from-reporter arguments."
            )
            return

        self.setup_s3_clients()
        self.process_crosswalks(self.reporter, self.resume)

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
        self, specific_reporter: str | None, resume: bool
    ) -> None:
        """Process crosswalk files for importing PDFs.

        :param specific_reporter: Specific reporter to process, if any.
        :param resume: Whether to resume from the last completed reporter.
        :return: None
        """
        logger.info(
            "Processing crosswalks. Specific reporter: %s, Resume: %s, Workers: %s",
            specific_reporter,
            self.resume,
            self.max_workers,
        )
        # Find all json files
        reporters_files = sorted(os.listdir(self.crosswalk_dir))
        reporters_files = [r for r in reporters_files if ".json" in r]

        # Generate a list of reporters available
        reporters = [
            r.replace(".json", "").replace("_", ".").replace("..", ". ")
            for r in reporters_files
        ]

        last_reporter_file = os.path.join(
            self.crosswalk_dir, "last_completed_reporter.txt"
        )

        # Load the last completed reporter if resuming
        if resume:
            try:
                with open(last_reporter_file) as f:
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

        if self.start_from_reporter:
            if self.start_from_reporter not in reporters:
                logger.error(
                    "Invalid reporter to start from: %s. Valid options: %s",
                    self.start_from_reporter,
                    reporters,
                )
                return
            else:
                reporter_item_index = reporters.index(self.start_from_reporter)
                if reporter_item_index:
                    # Update reporters and reporters files list
                    reporters = reporters[reporter_item_index:]
                    reporters_files = reporters_files[reporter_item_index:]
                    self.start_from_reporter = None

        for filename in reporters_files:
            if filename.endswith(".json"):
                reporter = (
                    filename.replace(".json", "")
                    .replace("_", ".")
                    .replace("..", ". ")
                )

                # Skip reporters until we reach the resume point
                if resume and last_completed_reporter:
                    if last_completed_reporter not in reporters:
                        logger.error(
                            "Invalid last completed reporter: %s. Valid options: %s",
                            last_completed_reporter,
                            reporters,
                        )
                        return

                    if reporter <= last_completed_reporter:
                        logger.info(
                            "Skipping already processed reporter: %s", reporter
                        )
                        continue

                if specific_reporter and reporter != specific_reporter:
                    continue

                logger.info("Starting to process reporter: %s", reporter)
                self.process_crosswalk_file(
                    os.path.join(self.crosswalk_dir, filename)
                )

                # Log the completed reporter
                logger.info("Completed processing reporter: %s", reporter)
                with open(last_reporter_file, "w") as f:
                    f.write(reporter)

    def process_entry(self, entry: dict[str, Any]) -> int:
        """Processes a single entry by attempting to download and store its associated
        PDF file
        :param entry: A dictionary containing details about the case entry.
        :return: An integer indicating the result of the process:
                 - 1 if the PDF was successfully downloaded and stored.
                 - 0 if the PDF was not downloaded (e.g., already processed, dry run
                 mode, or an error occurred).
        """
        logger.debug("Processing entry: %s", entry)
        try:
            cap_case_id = entry["cap_case_id"]
            cl_cluster_id = entry["cl_cluster_id"]
            json_path = entry["cap_path"]

            # Construct the PDF path based on the JSON path
            pdf_path = json_path.replace("cases", "case-pdfs").replace(
                ".json", ".pdf"
            )

            if pdf_path in self.processed_pdfs:
                logger.info("Skipping already processed PDF: %s", pdf_path)
                # Early abort
                return 0

            logger.info("Processing PDF: %s", pdf_path)

            if not self.dry_run:
                cluster = OpinionCluster.objects.get(id=cl_cluster_id)
                if not cluster.filepath_pdf_harvard:
                    # We don't have the pdf file yet
                    pdf_content = self.fetch_pdf_from_cap(pdf_path)
                    if pdf_content:
                        self.store_pdf_in_cl(cluster, pdf_content)
                        self.processed_pdfs.add(pdf_path)
                        # Successfully downloaded and stored
                        return 1
                else:
                    logger.info(
                        "Cluster: %s already has a PDF file assigned: %s",
                        cl_cluster_id,
                        pdf_path,
                    )
            else:
                logger.info("Dry run: Would fetch PDF from %s", pdf_path)

        except OpinionCluster.DoesNotExist:
            logger.error(
                "Cluster id: %s doesn't exist.",
                entry.get("cl_cluster_id", "Unknown"),
            )
        except KeyError as e:
            logger.error(
                "Missing key in entry: %s. Entry: %s",
                e,
                json.dumps(entry, indent=2),
            )
        except Exception as e:
            logger.exception(
                "Error processing CAP ID %s: %s",
                entry.get("cap_case_id", "Unknown"),
                str(e),
            )

        # No files downloaded
        return 0

    def process_crosswalk_file(self, crosswalk_file: str) -> None:
        """Process a single crosswalk file.

        :param crosswalk_file: Path to the crosswalk file.
        :return: None
        """
        logger.info("Processing crosswalk file: %s", crosswalk_file)

        start_time = time.time()

        with open(crosswalk_file) as f:
            crosswalk_data = json.load(f)
            logger.info("Documents to download: %s", len(crosswalk_data))

        total_downloaded = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_entry = {
                executor.submit(self.process_entry, entry): entry
                for entry in crosswalk_data
            }

            for future in as_completed(future_to_entry):
                entry = future_to_entry[future]
                try:
                    result = future.result()
                    if result is not None:
                        total_downloaded += result
                except Exception as e:
                    logger.error(
                        "Error processing entry %s: %s", entry, str(e)
                    )

        total_time = time.time() - start_time
        logger.info(
            "Finished processing all entries in the crosswalk file: %s - Total time: %.2f seconds. Total files downloaded: %s",
            crosswalk_file,
            total_time,
            total_downloaded,
        )

    def parse_cap_path(self, cap_path: str) -> tuple[str, str, str]:
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

    def fetch_pdf_from_cap(self, pdf_path: str) -> bytes | None:
        """Fetch PDF content from CAP.

        :param pdf_path: Path to the PDF in CAP storage.
        :return: PDF content as bytes, or None if fetching fails.
        """
        logger.info("Fetching PDF from CAP: %s", pdf_path)
        logger.debug("Bucket name: %s", self.cap_bucket_name)

        pdf_path = pdf_path.lstrip("/")

        if self.dry_run:
            logger.info("Dry run: Would fetch PDF from %s", pdf_path)
            return b"Mock PDF content"

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                logger.debug("Attempting to download file: %s", pdf_path)
                self.cap_client.download_file(
                    self.cap_bucket_name, pdf_path, temp_file.name
                )
                with open(temp_file.name, "rb") as f:
                    pdf_content = f.read()
                logger.debug(
                    "Downloaded PDF to temporary file: %s", temp_file.name
                )
                logger.debug("Read PDF content, length: %s", len(pdf_content))
                return pdf_content
        except Exception as e:
            logger.exception(
                "Error fetching PDF from CAP: %s",
                str(e),
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
        logger.info("Storing PDF for cluster: %s", cluster.id)
        storage = HarvardPDFStorage()
        file_path = f"harvard_pdf/{cluster.pk}.pdf"
        logger.debug("Saving file to: %s", file_path)

        try:
            content_file = ContentFile(pdf_content)

            saved_path = storage.save(file_path, content_file)
            logger.info("File saved successfully at: %s", saved_path)

            cluster.filepath_pdf_harvard = saved_path
            cluster.save()
            logger.info(
                "Cluster updated. filepath_pdf_harvard: %s",
                cluster.filepath_pdf_harvard,
            )
        except Exception as e:
            logger.exception(
                "Error saving PDF for cluster %s: %s",
                cluster.id,
                str(e),
            )


if __name__ == "__main__":
    import sys

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
