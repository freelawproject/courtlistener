import csv
import io
from itertools import batched
from typing import Any

import boto3
from django.core.management import CommandParser  # type: ignore
from django.db import connections

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import get_redis_interface
from cl.search.models import SEARCH_TYPES

s3_client = boto3.client("s3")


def get_total_number_of_records(type: str, options: dict[str, Any]) -> int:
    """
    Retrieves the total number of records for a specific data type.

    Args:
        type (str): The type of data to count. Must be one of the valid values
            from the `SEARCH_TYPES` class.
        options (dict[str, Any]): A dictionary containing options for filtering
            the results.
            - 'use_replica' (bool, optional): Whether to use the replica database
              connection (default: False).
            - 'random_sample_percentage' (float, optional): The percentage of
            records  to include in a random sample.

    Returns:
        int: The total number of records matching the specified data type.
    """
    match type:
        case SEARCH_TYPES.RECAP_DOCUMENT:
            base_query = (
                "SELECT count(*) AS exact_count FROM search_recapdocument"
            )
            filter_clause = """
            WHERE is_available=True AND page_count>0 AND ocr_status!=1
            """
        case SEARCH_TYPES.OPINION:
            base_query = "SELECT count(*) AS exact_count FROM search_opinion"
            filter_clause = "WHERE extracted_by_ocr != true"
        case SEARCH_TYPES.ORAL_ARGUMENT:
            base_query = "SELECT count(*) AS exact_count FROM audio_audio"
            filter_clause = """WHERE local_path_mp3 != '' AND
                download_url != 'https://www.cadc.uscourts.gov/recordings/recordings.nsf/' AND
                position('Unavailable' in download_url) = 0 AND
                duration > 30
            """

    if options["random_sample_percentage"]:
        percentage = options["random_sample_percentage"]
        base_query = f"{base_query} TABLESAMPLE SYSTEM ({percentage})"

    query = f"{base_query}\n {filter_clause}\n"
    with connections[
        "replica" if options["use_replica"] else "default"
    ].cursor() as cursor:
        cursor.execute(query, [])
        result = cursor.fetchone()

    return int(result[0])


def get_custom_query(
    type: str, last_pk: str, options: dict[str, Any]
) -> tuple[str, list[Any]]:
    """
    Generates a custom SQL query based on the provided type and optional last
    pk.

    Args:
        type (str): Type of data to retrieve.
        last_pk (int, optional): Last primary key retrieved in a previous
            query. Defaults to None.
        options (dict[str, Any]): A dictionary containing options for filtering
            the results.
            - 'random_sample_percentage' (float, optional): The percentage of
            records to include in a random sample.

    Returns:
        tuple[str, list[Any]]: A tuple containing the constructed SQL
            query(str) and a list of parameters (list[Any]) to be used with
            the query.
    """
    params = []
    random_sample = options["random_sample_percentage"]
    match type:
        case SEARCH_TYPES.RECAP_DOCUMENT:
            base_query = "SELECT id from search_recapdocument"
            filter_clause = (
                "WHERE is_available=True AND page_count>0 AND ocr_status!=1"
            )
        case SEARCH_TYPES.OPINION:
            base_query = "SELECT id from search_opinion"
            filter_clause = "WHERE extracted_by_ocr != true"
        case SEARCH_TYPES.ORAL_ARGUMENT:
            base_query = "SELECT id from audio_audio"
            filter_clause = """
            WHERE local_path_mp3 != '' AND
                download_url != 'https://www.cadc.uscourts.gov/recordings/recordings.nsf/' AND
                position('Unavailable' in download_url) = 0 AND
                duration > 30
            """

    if random_sample:
        base_query = f"{base_query} TABLESAMPLE SYSTEM ({random_sample})"

    if last_pk and not random_sample:
        filter_clause = f"{filter_clause} AND id > %s"
        params.append(last_pk)

    query = f"{base_query}\n {filter_clause}\n ORDER BY id\n LIMIT %s"

    return query, params


class Command(VerboseCommand):
    help = (
        "Retrieves data records from the database and creates manifest files"
        "listing those records in Amazon S3. These manifest files can then"
        "be used by batch processing jobs to efficiently process the data in"
        "parallel."
    )

    def add_arguments(self, parser: CommandParser):
        parser.add_argument(
            "--record-type",
            type=str,
            choices=[
                SEARCH_TYPES.RECAP_DOCUMENT,
                SEARCH_TYPES.OPINION,
                SEARCH_TYPES.ORAL_ARGUMENT,
            ],
            help=(
                "Which type of records do you want to import?"
                f"({', '.join([SEARCH_TYPES.PEOPLE, SEARCH_TYPES.RECAP_DOCUMENT, SEARCH_TYPES.OPINION])})"
            ),
            required=True,
        )
        parser.add_argument(
            "--bucket-name",
            help="The name of the bucket to store documents.",
            required=True,
        )
        parser.add_argument(
            "--query-batch-size",
            type=int,
            default=1_000_000,
            help="The number of items to retrieve in a single query.",
        )
        parser.add_argument(
            "--lambda-record-size",
            type=int,
            default=100,
            help="The number of records to process in a single lambda.",
        )
        parser.add_argument(
            "--use-replica",
            action="store_true",
            default=False,
            help="Use this flag to run the queries in the replica db",
        )
        parser.add_argument(
            "--file-name",
            type=str,
            default=None,
            help="Custom name for the output files. If not provided, a default "
            "name will be used.",
        )
        parser.add_argument(
            "--random-sample-percentage",
            type=float,
            default=None,
            help="Specifies the proportion of the table to be sampled (between "
            "0.0 and 100.0). Use this flag to retrieve a random set of records.",
        )

    def handle(self, *args, **options):
        r = get_redis_interface("CACHE")

        record_type = options["record_type"]
        bucket_name = options["bucket_name"]

        last_pk = r.hget(f"{record_type}_import_status", "last_pk")
        if last_pk:
            logger.info(
                f"Found a PK in cache, starting import process from record {last_pk}."
            )

        total_number_of_records = int(
            r.hget(f"{record_type}_import_status", "total_records") or 0
        )
        if not total_number_of_records:
            total_number_of_records = get_total_number_of_records(
                record_type, options
            )
            r.hset(
                f"{record_type}_import_status",
                "total_records",
                total_number_of_records,
            )

        counter = int(
            r.hget(f"{record_type}_import_status", "next_iteration_counter")
            or 0
        )
        file_name = (
            options["file_name"]
            if options["file_name"]
            else f"{record_type}_filelist"
        )
        while True:
            query, params = get_custom_query(
                options["record_type"], last_pk, options
            )
            if not options["random_sample_percentage"]:
                params.append(options["query_batch_size"])

            with connections[
                "replica" if options["use_replica"] else "default"
            ].cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                record_count = cursor.rowcount

            if not record_count:
                logger.info("Finished all the records!")
                break

            # Write the content of the csv file to a buffer and upload it
            with io.StringIO() as csvfile:
                writer = csv.DictWriter(
                    csvfile,
                    fieldnames=["bucket", "file_name"],
                    extrasaction="ignore",
                )
                for row in batched(rows, options["lambda_record_size"]):
                    if options["random_sample_percentage"]:
                        # Create an underscore-separated file name that lambda
                        # can split and use as part of batch processing.
                        ids = [str(r[0]) for r in row]
                        content = "_".join(ids)
                    else:
                        content = (
                            f"{row[0][0]}_{row[-1][0]}"
                            if len(row) > 1
                            else f"{row[0][0]}"
                        )
                    query_dict = {
                        "bucket": bucket_name,
                        "file_name": content,
                    }
                    writer.writerow(query_dict)

                s3_client.put_object(
                    Key=f"{file_name}_{counter}.csv",
                    Bucket=bucket_name,
                    Body=csvfile.getvalue().encode("utf-8"),
                )

            if options["random_sample_percentage"]:
                # Due to the non-deterministic nature of random sampling,
                # storing data to recover the query for future executions
                # wouldn't be meaningful. Random queries are unlikely to
                # produce the same results on subsequent runs.
                logger.info(f"Finished processing {record_count} records")
                break

            counter += 1
            last_pk = rows[-1][0]
            records_processed = int(
                r.hget(f"{record_type}_import_status", "records_processed")
                or 0
            )

            # Store the results of this iteration and log the progress
            r.hset(
                f"{record_type}_import_status",
                mapping={
                    "last_pk": last_pk,
                    "next_iteration_counter": counter,
                    "records_processed": records_processed + record_count,
                },
            )
            logger.info(
                "\rRetrieved {}/{}, ({:.0%}), last PK processed: {},".format(
                    record_count + records_processed,
                    total_number_of_records,
                    (record_count + records_processed)
                    * 1.0
                    / total_number_of_records,
                    last_pk,
                )
            )

        # Removes the key from the cache after a succesfull execution
        r.delete(f"{record_type}_import_status")
