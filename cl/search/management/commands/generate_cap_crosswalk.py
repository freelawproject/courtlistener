import json
import logging
import os
from datetime import datetime, timedelta

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from tqdm import tqdm

from cl.lib.command_utils import CommandUtils
from cl.search.models import Citation, Court, OpinionCluster

logger = logging.getLogger(__name__)


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
            help="Directory to save crosswalk files (default: cl/search/crosswalks)",
        )

    def handle(self, *args, **options):
        if options["verbose"]:
            logger.setLevel(logging.DEBUG)

        self.dry_run = options["dry_run"]
        self.single_reporter = options["reporter"]
        self.single_volume = options["volume"]
        self.output_dir = options["output_dir"] or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "crosswalks",
        )

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.setup_s3_client()
        self.total_cases_processed = 0
        self.total_matches_found = 0
        self.generate_complete_crosswalk()

        self.print_statistics()

    def setup_s3_client(self, mock_client=None):
        # Set up S3 client for accessing CAP data in R2. Ensure env has appropriate values set
        if mock_client:
            self.s3_client = mock_client
        else:
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=settings.R2_ENDPOINT_URL,
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            )
        self.bucket_name = settings.R2_BUCKET_NAME

    def generate_complete_crosswalk(self):
        reporters = self.fetch_reporters_metadata()

        if self.single_reporter:
            reporters = [
                r for r in reporters if r["short_name"] == self.single_reporter
            ]

        for i, reporter in enumerate(
            tqdm(reporters, desc="Processing reporters")
        ):
            self.generate_crosswalk_for_reporter(reporter, i)

    def generate_crosswalk_for_reporter(self, reporter, index):
        crosswalk = []
        reporter_name = reporter["short_name"]
        volumes = self.fetch_volumes_for_reporter(reporter["slug"])

        if self.single_volume:
            volumes = (
                [str(self.single_volume)]
                if str(self.single_volume) in volumes
                else []
            )

        for volume in volumes:
            cases_metadata = self.fetch_cases_metadata(
                reporter["slug"], volume
            )
            logger.info(
                f"Processing {len(cases_metadata)} cases for {reporter_name} volume {volume}"
            )

            # Sort cases by ID to ensure consistent processing order
            cases_metadata.sort(key=lambda x: x["id"])

            for case_meta in cases_metadata:
                self.total_cases_processed += 1
                if self.is_valid_case_metadata(case_meta):
                    cl_case = self.find_matching_case(case_meta)
                    if cl_case:
                        self.total_matches_found += 1
                        crosswalk.append(
                            {
                                "cap_id": case_meta["id"],
                                "cl_id": cl_case.id,
                                "cap_path": f"/{reporter['slug']}/{volume}/cases/{case_meta['file_name']}.json",
                            }
                        )
                        logger.info(
                            f"Match found: CAP ID {case_meta['id']} -> CL ID {cl_case.id}"
                        )
                    else:
                        logger.info(
                            f"No match found for CAP ID {case_meta['id']}"
                        )

            if not self.dry_run:
                self.save_crosswalk(crosswalk, reporter_name, index)
            else:
                logger.info(
                    f"Dry run: Would save {len(crosswalk)} matches for {reporter_name}"
                )

            logger.info(
                f"Processed {self.total_cases_processed} cases for {reporter_name}, found {self.total_matches_found} matches"
            )

    def fetch_volumes_for_reporter(self, reporter_slug):
        # Fetch volume directories for a given reporter from R2
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=f"{reporter_slug}/",
                Delimiter="/",
            )
            volume_directories = [
                o["Prefix"].split("/")[-2]
                for o in response.get("CommonPrefixes", [])
            ]
            return sorted(volume_directories)
        except Exception as e:
            logger.error(
                f"Error fetching volume directories for {reporter_slug}: {str(e)}"
            )
            return []

    def find_matching_case(self, case_meta):
        try:
            citation = case_meta["citations"][0]["cite"].split()
            volume, reporter, page = citation[0], citation[1], citation[2]

            logger.debug(f"Searching for citation: {volume} {reporter} {page}")

            matches = OpinionCluster.objects.filter(
                citations__volume=volume,
                citations__reporter=reporter,
                citations__page=page,
            ).distinct()

            match_count = matches.count()

            if match_count == 1:
                matched_case = matches.first()
                logger.debug(
                    f"Single match found: {matched_case.case_name} (CL ID: {matched_case.id})"
                )
                return matched_case
            elif match_count > 1:
                logger.warning(
                    f"Multiple matches ({match_count}) found for citation: {volume} {reporter} {page}"
                )
                return (
                    matches.first()
                )  # Return the first match, but log a warning
            else:
                logger.debug(
                    f"No match found for citation: {volume} {reporter} {page}"
                )

        except Exception as e:
            logger.error(
                f"Error processing case {case_meta.get('id', 'Unknown ID')}: {str(e)}",
                exc_info=True,
            )

        return None

    def fetch_cases_metadata(self, reporter_slug, volume):
        # Fetch CasesMetadata.json for a specific reporter and volume from R2
        key = f"{reporter_slug}/{volume}/CasesMetadata.json"
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name, Key=key
            )
            return json.loads(response["Body"].read().decode("utf-8"))
        except Exception as e:
            logger.error(
                f"Error fetching CasesMetadata.json for {reporter_slug} volume {volume}: {str(e)}"
            )
            return []

    def fetch_reporters_metadata(self):
        # Fetch ReportersMetadata.json from R2
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name, Key="ReportersMetadata.json"
            )
            return json.loads(response["Body"].read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Error fetching ReportersMetadata.json: {str(e)}")
            return []

    def is_valid_case_metadata(self, case_meta):
        # Check if case metadata contains all required fields
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

    def print_statistics(self):
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

    def save_crosswalk(self, crosswalk, reporter_name, index):
        filename = f"{reporter_name.replace(' ', '_').replace('.', '_')}.json"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(crosswalk, f, indent=2)
        self.stdout.write(self.style.SUCCESS(f"Saved crosswalk to {filepath}"))


if __name__ == "__main__":
    import sys

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
