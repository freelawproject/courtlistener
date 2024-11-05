import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
import pytz
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand
from tqdm import tqdm

from cl.lib.command_utils import CommandUtils
from cl.search.models import OpinionCluster

logger = logging.getLogger(__name__)

# Note: To run this command, you need to set up the following environment variables:
# CAP_R2_ENDPOINT_URL, CAP_R2_ACCESS_KEY_ID, CAP_R2_SECRET_ACCESS_KEY, and CAP_R2_BUCKET_NAME
# These values must be obtained from the Harvard CAP DevOps team.
# Ensure these are properly configured in your environment before executing this command.

# Example of generated crosswalk file:

# [
#   {
#     "cap_case_id": 3,
#     "cl_cluster_id": 1,
#     "cap_path": "/test/100/cases/0036-01.json"
# },
# {
#     "cap_case_id": 4,
#     "cl_cluster_id": 2,
#     "cap_path": "/test/100/cases/0040-01.json"
# }
# ]


class Command(CommandUtils, BaseCommand):
    help = "Generate a comprehensive crosswalk between CAP and CourtListener cases using only CasesMetadata.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reporter", type=str, help="Process only this reporter"
        )
        parser.add_argument(
            "--volume", type=int, help="Process only this volume"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Perform a dry run without saving crosswalk",
        )
        parser.add_argument(
            "--verbose", action="store_true", help="Increase output verbosity"
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            help="Directory to save crosswalk files",
            required=True,
        )
        parser.add_argument(
            "--start-from-reporter",
            type=str,
            help="Process starting from this reporter slug",
        )
        parser.add_argument(
            "--updated-after",
            type=str,
            help="Only process cases updated after this date (format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS+00:00)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["verbose"]:
            logger.setLevel(logging.DEBUG)

        self.dry_run = options["dry_run"]
        self.single_reporter = options["reporter"]
        self.single_volume = options["volume"]
        self.output_dir = options["output_dir"]
        self.start_from_reporter = options["start_from_reporter"]
        self.updated_after = None
        if options["updated_after"]:
            try:
                self.updated_after = datetime.fromisoformat(
                    options["updated_after"]
                )
            except ValueError:
                try:
                    self.updated_after = datetime.strptime(
                        options["updated_after"], "%Y-%m-%d"
                    )
                    # Set time to start of day in UTC
                    self.updated_after = self.updated_after.replace(
                        tzinfo=pytz.UTC
                    )
                except ValueError:
                    raise ValueError(
                        "Invalid date format. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS+00:00"
                    )

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.setup_s3_client()
        self.total_cases_processed = 0
        self.total_matches_found = 0
        self.generate_complete_crosswalk()

        self.print_statistics()

    def setup_s3_client(self, mock_client: Optional[Any] = None) -> None:
        """Set up S3 client for accessing CAP data in R2.

        :param mock_client: Optional mock client for testing.
        :return: None
        """
        if mock_client:
            self.s3_client = mock_client
        else:
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=settings.CAP_R2_ENDPOINT_URL,
                aws_access_key_id=settings.CAP_R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.CAP_R2_SECRET_ACCESS_KEY,
            )
        self.bucket_name = settings.CAP_R2_BUCKET_NAME

    def generate_complete_crosswalk(self) -> None:
        """Generate a complete crosswalk for all reporters or a specific reporter.

        :return: No return, generates and saves the crosswalk file
        """

        reporters = self.fetch_reporters_metadata()

        if self.single_reporter:
            reporters = [
                r for r in reporters if r["short_name"] == self.single_reporter
            ]

        if self.start_from_reporter:
            reporter_item_index = next(
                (
                    index
                    for index, item in enumerate(reporters)
                    if item["slug"] == self.start_from_reporter
                ),
                None,
            )
            if reporter_item_index:
                logger.info(
                    f"Starting from reporter: {self.start_from_reporter}"
                )
                reporters = reporters[reporter_item_index:]
                self.start_from_reporter = None
            else:
                # Invalid reporter slug
                raise ValueError(
                    f"Invalid reporter slug to start from: {self.start_from_reporter}"
                )

        for i, reporter in enumerate(
            tqdm(reporters, desc="Processing reporters")
        ):
            self.generate_crosswalk_for_reporter(reporter, i)

    def generate_crosswalk_for_reporter(
        self, reporter: Dict[str, Any], index: int
    ) -> None:
        """Generate crosswalk for a specific reporter.

        :param reporter: Dictionary containing reporter metadata.
        :param index: Index of the reporter being processed.
        :return: None
        """
        crosswalk = []
        reporter_name = reporter["short_name"]
        reporter_slug = reporter["slug"]
        volumes = self.fetch_volumes_for_reporter(reporter_slug)

        if self.single_volume:
            volumes = (
                [str(self.single_volume)]
                if str(self.single_volume) in volumes
                else []
            )

        for volume in volumes:
            cases_metadata = self.fetch_cases_metadata(reporter_slug, volume)
            logger.info(
                f"Processing {len(cases_metadata)} cases for {reporter_name} volume {volume}"
            )

            for case_meta in cases_metadata:
                logger.debug(
                    f"Processing case: {case_meta['id']} - {case_meta['name_abbreviation']}"
                )
                if self.is_valid_case_metadata(case_meta):
                    # Only increment the counter for valid cases that meet our date criteria
                    self.total_cases_processed += 1
                    cl_case = self.find_matching_case(
                        case_meta, reporter_slug, volume
                    )
                    if cl_case:
                        self.total_matches_found += 1
                        crosswalk.append(
                            {
                                "cap_case_id": case_meta["id"],
                                "cl_cluster_id": cl_case.id,
                                "cap_path": f"/{reporter_slug}/{volume}/cases/{case_meta['file_name']}.json",
                            }
                        )
                        logger.info(
                            f"Match found: CAP ID {case_meta['id']} -> CL ID {cl_case.id}"
                        )
                else:
                    logger.warning(
                        f"Invalid case metadata for CAP ID {case_meta['id']}"
                    )

            if not self.dry_run:
                self.save_crosswalk(crosswalk, reporter_name, index)
            else:
                logger.info(
                    f"Dry run: Would save {len(crosswalk)} matches for {reporter_name}"
                )

            logger.info(
                f"Processed {self.total_cases_processed} cases for {reporter_name}({reporter_slug}), found {self.total_matches_found} matches"
            )

    def fetch_volumes_for_reporter(self, reporter_slug: str) -> List[str]:
        """Fetch volume directories for a given reporter from R2 using a paginator.

        :param reporter_slug: The slug of the reporter.
        :return: A list of volume directory names.
        """
        volume_directories = []

        try:
            # Create a paginator
            paginator = self.s3_client.get_paginator("list_objects_v2")

            page_iterator = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=f"{reporter_slug}/",
                Delimiter="/",
            )

            for page in page_iterator:
                volume_directories.extend(
                    [
                        o["Prefix"].split("/")[-2]
                        for o in page.get("CommonPrefixes", [])
                    ]
                )

            logger.info(
                f"Found {len(volume_directories)} volumes for reporter {reporter_slug}"
            )

        except ClientError as e:
            logger.error(
                f"Error fetching volume directories for {reporter_slug}: {str(e)}"
            )

        return sorted(volume_directories)

    def find_matching_case(
        self, case_meta: Dict[str, Any], reporter_slug: str, volume: str
    ) -> Optional[OpinionCluster]:
        """Find a matching case in CourtListener database using the filepath_json_harvard field.

        :param case_meta: Case metadata dictionary from CAP.
        :param reporter_slug: The slug of the reporter.
        :param volume: The volume number.
        :return: An OpinionCluster object if a match is found, otherwise None.
        """
        try:
            cap_case_id = str(case_meta["id"])
            page = str(case_meta["first_page"])

            query = f"law.free.cap.{reporter_slug}.{volume}/{page}.{cap_case_id}.json"
            logger.debug(f"Searching for: {query}")

            # Exact match of the file path in this format, e.g.:
            # law.free.cap.wis-2d.369/658.6776082.json
            matching_cluster = OpinionCluster.objects.filter(
                filepath_json_harvard=query
            ).first()

            if matching_cluster:
                # Match found, return object
                return matching_cluster
            else:
                logger.info(
                    f"No match found for CAP ID {cap_case_id} (reporter: {reporter_slug}, volume: {volume}, page: {page})"
                )

        except Exception as e:
            logger.error(
                f"Error processing case {str(case_meta["id"])}: {str(e)}",
                exc_info=True,
            )

        return None

    def fetch_cases_metadata(
        self, reporter_slug: str, volume: str
    ) -> List[Dict[str, Any]]:
        """Fetch CasesMetadata.json for a specific reporter and volume from R2.

        :param reporter_slug: The slug of the reporter.
        :param volume: The volume number.
        :return: A list of case metadata dictionaries.
        """
        key = f"{reporter_slug}/{volume}/CasesMetadata.json"
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name, Key=key
            )
            cases = json.loads(response["Body"].read().decode("utf-8"))

            # Filter cases by last_updated if specified
            if self.updated_after:
                cases = [
                    case
                    for case in cases
                    if "last_updated" in case
                    and datetime.fromisoformat(case["last_updated"])
                    > self.updated_after
                ]
                logger.debug(
                    f"Filtered to {len(cases)} cases after {self.updated_after}"
                )

            return cases
        except Exception as e:
            logger.error(
                f"Error fetching CasesMetadata.json for {reporter_slug} volume {volume}: {str(e)}"
            )
            return []

    def fetch_reporters_metadata(self) -> List[Dict[str, Any]]:
        """Fetch ReportersMetadata.json from R2.

        :return: A list of reporter metadata dictionaries.
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name, Key="ReportersMetadata.json"
            )
            return json.loads(response["Body"].read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Error fetching ReportersMetadata.json: {str(e)}")
            return []

    def is_valid_case_metadata(self, case_meta: Dict[str, Any]) -> bool:
        """Check if case metadata contains all required fields.

        :param case_meta: Case metadata dictionary.
        :return: True if metadata is valid, False otherwise.
        """
        required_fields = [
            "id",
            "name_abbreviation",
            "decision_date",
            "citations",
            "file_name",
        ]
        return (
            all(field in case_meta for field in required_fields)
            and case_meta["citations"]
        )

    def print_statistics(self) -> None:
        """Print statistics about the crosswalk generation process.

        :return: None
        """
        self.stdout.write(
            self.style.SUCCESS(
                f"Total cases processed from R2: {self.total_cases_processed}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Total matches found: {self.total_matches_found}"
            )
        )
        if self.total_cases_processed > 0:
            match_rate = (
                self.total_matches_found / self.total_cases_processed
            ) * 100
            self.stdout.write(
                self.style.SUCCESS(f"Match rate: {match_rate:.2f}%")
            )
        else:
            self.stdout.write(self.style.WARNING("No cases processed"))

    def save_crosswalk(
        self, crosswalk: List[Dict[str, Any]], reporter_name: str, index: int
    ) -> None:
        """Save the generated crosswalk to a JSON file.

        :param crosswalk: List of crosswalk entries.
        :param reporter_name: Name of the reporter.
        :param index: Index of the reporter being processed.
        :return: None
        """
        filename = f"{reporter_name.replace(' ', '_').replace('.', '_')}.json"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(crosswalk, f, indent=2)
        self.stdout.write(self.style.SUCCESS(f"Saved crosswalk to {filepath}"))


if __name__ == "__main__":
    import sys

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
