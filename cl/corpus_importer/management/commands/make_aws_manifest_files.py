import csv
import io
from datetime import datetime
from itertools import batched
from typing import Any

import boto3
from django.core.management import CommandParser  # type: ignore
from django.db import connections
from django.db.models import Q
from django.utils import timezone
from redis import Redis

from cl.audio.models import Audio
from cl.disclosures.models import (
    Agreement,
    Debt,
    FinancialDisclosure,
    Gift,
    Investment,
    NonInvestmentIncome,
)
from cl.disclosures.models import Position as FDPosition
from cl.disclosures.models import Reimbursement, SpouseIncome
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.models import AbstractDateTimeModel
from cl.lib.redis_utils import get_redis_interface
from cl.people_db.models import (
    ABARating,
    Education,
    Person,
    PoliticalAffiliation,
    Position,
    Source,
)
from cl.search.models import SEARCH_TYPES, Opinion

s3_client = boto3.client("s3")

JUDICIAL_POSITIONS: list[str] = [
    key
    for key, value in Position.POSITION_TYPE_GROUPS.items()
    if value == "Judge"
]


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
    params: list[Any] = []
    match type:
        case SEARCH_TYPES.RECAP_DOCUMENT:
            base_query = (
                "SELECT count(*) AS exact_count FROM search_recapdocument"
            )
            filter_clause = """
            WHERE is_available=True AND page_count>0 AND ocr_status!=1
            """
        case SEARCH_TYPES.OPINION:
            base_query = (
                "SELECT count(*) AS exact_count "
                "FROM search_opinion O "
                "INNER JOIN search_opinioncluster OC ON O.cluster_id = OC.id"
            )
            filter_clause = (
                "WHERE (extracted_by_ocr != true OR OC.source LIKE %s)"
            )
            params.append("%U%")
        case SEARCH_TYPES.ORAL_ARGUMENT:
            base_query = "SELECT count(*) AS exact_count FROM audio_audio"
            filter_clause = """WHERE local_path_mp3 != '' AND
                download_url != 'https://www.cadc.uscourts.gov/recordings/recordings.nsf/' AND
                position('Unavailable' in download_url) = 0 AND
                duration > 30
            """
        case SEARCH_TYPES.PEOPLE:
            base_query = (
                "SELECT count(DISTINCT P.id) "
                "FROM people_db_person P "
                "JOIN people_db_position POS ON P.id = POS.person_id"
            )
            filter_clause = "WHERE POS.position_type=ANY(%s)"
            params.append(JUDICIAL_POSITIONS)
        case "fd":
            base_query = "SELECT count(*) AS exact_count FROM disclosures_financialdisclosure"
            filter_clause = ""

    if options["random_sample_percentage"]:
        percentage = options["random_sample_percentage"]
        base_query = f"{base_query} TABLESAMPLE SYSTEM ({percentage})"

    query = (
        f"{base_query}\n"
        if options["all_records"]
        else f"{base_query}\n {filter_clause}\n"
    )
    with connections[
        "replica" if options["use_replica"] else "default"
    ].cursor() as cursor:
        cursor.execute(query, params)
        result = cursor.fetchone()

    return int(result[0])


def get_custom_query(
    type: str, last_pk: str | None, options: dict[str, Any]
) -> tuple[str, list[Any]]:
    """
    Generates a custom SQL query based on the provided type and optional last
    pk.

    Args:
        type (str): Type of data to retrieve.
        last_pk (str, optional): Last primary key retrieved in a previous
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
    params: list[Any] = []
    random_sample = options["random_sample_percentage"]
    match type:
        case SEARCH_TYPES.RECAP_DOCUMENT:
            base_query = "SELECT id from search_recapdocument"
            filter_clause = (
                "WHERE is_available=True AND page_count>0 AND ocr_status!=1"
            )
        case SEARCH_TYPES.OPINION:
            base_query = (
                "SELECT O.id "
                "FROM search_opinion O "
                "INNER JOIN search_opinioncluster OC ON O.cluster_id = OC.id"
            )
            filter_clause = (
                "WHERE (extracted_by_ocr != true OR OC.source LIKE %s)"
            )
            params.append("%U%")
        case SEARCH_TYPES.ORAL_ARGUMENT:
            base_query = "SELECT id from audio_audio"
            filter_clause = """
            WHERE local_path_mp3 != '' AND
                download_url != 'https://www.cadc.uscourts.gov/recordings/recordings.nsf/' AND
                position('Unavailable' in download_url) = 0 AND
                duration > 30
            """
        case SEARCH_TYPES.PEOPLE:
            base_query = (
                "SELECT DISTINCT P.id "
                "FROM people_db_person P "
                "JOIN people_db_position POS ON P.id = POS.person_id"
            )
            filter_clause = "WHERE POS.position_type=ANY(%s)"
            params.append(JUDICIAL_POSITIONS)
        case "fd":
            base_query = "SELECT id FROM disclosures_financialdisclosure"
            filter_clause = ""

    if random_sample:
        base_query = f"{base_query} TABLESAMPLE SYSTEM ({random_sample})"

    if options["all_records"]:
        filter_clause = ""

    # Using a WHERE clause with `id > last_pk` and a LIMIT clause for batch
    # retrieval is not suitable for random sampling. The following logic
    # removes these clauses when retrieving a random sample to ensure all rows
    # have an equal chance of being selected.
    if last_pk and not random_sample:
        match type:
            case SEARCH_TYPES.OPINION:
                base_id = "O.id"
            case SEARCH_TYPES.PEOPLE:
                base_id = "P.id"
            case _:
                base_id = "id"
        filter_clause = (
            f"WHERE {base_id} > %s"
            if not filter_clause
            else f"{filter_clause} AND {base_id} > %s"
        )
        params.append(last_pk)

    query = (
        f"{base_query}\n {filter_clause}"
        if random_sample
        else f"{base_query}\n {filter_clause}\n ORDER BY id\n LIMIT %s"
    )

    return query, params


def upload_manifest(
    record_ids: list[tuple[int]],
    base_filename: str,
    options: dict[str, Any],
    batch_counter: int | None = None,
) -> None:
    """
    Generates a CSV manifest file containing S3 object keys derived from record
    ID batches and uploads it to the specified S3 bucket.

    The S3 object keys within the manifest are constructed based on the
    provided`record_ids`. When certain conditions are met, the individual
    record IDs within a batch will be joined by underscores in the object key.
    These conditions are:

    - When records are randomly sampled.
    - During monthly export processes.
    - When explicitly specified through the `options` dictionary.

    Args:
        rows (list[tuple[int]]): A list of tuples, where each tuple contains at
            least the record's unique ID
        filename (str): The base name for the manifest file in S3.
        options (dict[str, Any]): A dictionary containing configuration options
            including:
            - "bucket_name" (str): The name of the S3 bucket.
            - "lambda_record_size" (int): The number of records to group into
                each batch.
            - "random_sample_percentage" (float, optional): If set, indicates
                that records are randomly sampled, and manifest should contain
                all IDs separated by underscores.
            - "save_ids_as_sequence" (bool, optional): If True, manifest should
                contain all IDs in the batch separated by underscores.
        counter (int, optional): An optional integer to append to the filename
            for distinguishing between multiple manifest files.
    """
    bucket_name = options["bucket_name"]
    # Write the content of the csv file to a buffer and upload it
    with io.StringIO() as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["bucket", "file_name"],
            extrasaction="ignore",
        )
        for row in batched(record_ids, options["lambda_record_size"]):
            should_use_underscores = any(
                [
                    options["random_sample_percentage"],
                    options["save_ids_as_sequence"],
                    options["monthly_export"],
                ]
            )
            if should_use_underscores:
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
            query_dict = {"bucket": bucket_name, "file_name": content}
            writer.writerow(query_dict)

        name = (
            f"{base_filename}_{batch_counter}.csv"
            if batch_counter
            else base_filename
        )
        s3_client.put_object(
            Key=name,
            Bucket=bucket_name,
            Body=csvfile.getvalue().encode("utf-8"),
        )


def export_records_in_batches(
    r: Redis, record_type: str, options: dict[str, Any]
) -> None:
    """
    Sequentially exports records of a specific type from the database in batches,
    uploads manifests of the exported data, and tracks the progress using Redis.

    Args:
        r: An instance of the Redis client used for caching and progress
            tracking.
        record_type: The type of records to export. This is used to generate
            the database query and prefix for Redis keys.
        options: A dictionary containing configuration options for the export
            process:
            - 'file_name' (str, optional): The base filename for the generated
                manifest files.
            - 'query_batch_size' (int): The number of records to fetch from the
                database in each query.
            - 'use_replica' (bool): If True, queries will be executed
                against the 'replica' database connection (if configured).
            - 'random_sample_percentage' (float): If set (between 0 and 100), the
              export will retrieve a random sample of records.
    """

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
        r.hget(f"{record_type}_import_status", "next_iteration_counter") or 0
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

        upload_manifest(rows, file_name, options, counter)

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
            r.hget(f"{record_type}_import_status", "records_processed") or 0
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

    # Removes the key from the cache after a successful execution
    r.delete(f"{record_type}_import_status")


def get_records_modified_since(
    model: type[AbstractDateTimeModel], field_name: str, timestamp: datetime
) -> list[tuple[int]]:
    """
    Retrieves a list of tuples containing the values of a specified field
    for all instances of a given model that have been created or modified
    on or after a given timestamp.

    Args:
        model: The Django model class to query (must inherit from
            AbstractDateTimeModel and have 'date_created' and 'date_modified'
            fields).
        field_name: The name of the field whose values to retrieve.
        since_timestamp: The datetime object representing the lower bound
            (inclusive) for filtering based on creation or modification time.

    Returns:
        A list of tuples, where each tuple contains the value of the specified
        field for a matching model instance. For example, if 'field_name' is 'id',
        the return type would be List[(int,)].
    """
    # Construct a query to find objects created or modified on or after the given timestamp.
    queryset = model._default_manager.filter(
        Q(date_created__gte=timestamp) | Q(date_modified__gte=timestamp)
    )

    # Extract the values of the specified field from the filtered queryset.
    return list(queryset.values_list(field_name))


def get_monthly_record_ids_by_type(
    record_type: str, timestamp: datetime
) -> list[tuple[int]]:
    """
    Retrieves a list of unique IDs for records of a specific type that were
    created or modified after a given timestamp.

    The function handles different record types by querying the main model
    and any relevant nested/related models that might have been updated.

    Args:
        record_type: A string identifying the type of records to retrieve.
        timestamp: A datetime object representing the month for which to
            retrieve records.
        options: A dictionary containing any additional options.

    Returns:
        A list of unique integer IDs for the records of the specified type
        that were created or modified on or after the given `timestamp`.
    """
    related_field = "pk"
    main_model = None
    nested_models: list[type[AbstractDateTimeModel]] = []
    match record_type:
        case SEARCH_TYPES.OPINION:
            main_model = Opinion
            nested_models = []
        case SEARCH_TYPES.ORAL_ARGUMENT:
            main_model = Audio
            nested_models = []
        case SEARCH_TYPES.PEOPLE:
            main_model = Person
            nested_models = [
                Source,
                ABARating,
                Education,
                PoliticalAffiliation,
                Position,
            ]
            related_field = "person_id"
        case "fd":
            main_model = FinancialDisclosure
            nested_models = [
                Agreement,
                Debt,
                Gift,
                Investment,
                NonInvestmentIncome,
                Reimbursement,
                SpouseIncome,
                FDPosition,
            ]
            related_field = "financial_disclosure_id"
        case _:
            raise NotImplementedError(
                f"Record type '{record_type}' is not supported."
            )

    record_ids = []
    # check nested/related models
    for model in nested_models:
        record_ids.extend(
            get_records_modified_since(model, related_field, timestamp)
        )
    record_ids.extend(get_records_modified_since(main_model, "pk", timestamp))
    return list(set(record_ids))


def compute_monthly_export(
    record_type: str, timestamp: datetime, options: dict[str, Any]
):
    """
    Computes and uploads a monthly export manifest for a specified record type.

    The function determines the filename based on the record type and the
    month of the provided timestamp, retrieves the relevant record IDs, and
    then uploads the manifest.

    Args:
        record_type: The type of records to include in the export.
        export_timestamp: A datetime object representing the month for which
            to generate the export. The filename will be based on this
            timestamp.
        export_options: A dictionary containing options to be passed to the
            `upload_manifest` function.
    """
    filename = (
        f"{record_type}_monthly_export_{timestamp.month}_{timestamp.year}"
    )
    record_ids = get_monthly_record_ids_by_type(record_type, timestamp)
    upload_manifest(record_ids, filename, options)


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
                SEARCH_TYPES.PEOPLE,
                "fd",  # Type for financial disclosures
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
        parser.add_argument(
            "--all-records",
            action="store_true",
            default=False,
            help="Use this flag to retrieve all records from the table without"
            " applying any filters.",
        )
        parser.add_argument(
            "--save-ids-as-sequence",
            action="store_true",
            default=False,
            help="Store IDs in manifest files as a string sequence (e.g., '1_2_3') "
            "instead of a range (e.g., '1-3').",
        )
        parser.add_argument(
            "--monthly-export",
            action="store_true",
            default=False,
            help="Generate a monthly delta of records by querying changes "
            "since the previous successful export.",
        )

    def handle(self, *args, **options):
        r = get_redis_interface("CACHE")

        record_type = options["record_type"]
        monthly_export = options["monthly_export"]

        if monthly_export:
            last_export_key = f"bulk_import:{record_type}"
            last_export_timestamp = r.get(last_export_key)
            if not last_export_timestamp:
                return logger.info(
                    "Warning: No previous timestamp for bulk import found for "
                    f"record type: {record_type}."
                )
            compute_monthly_export(
                record_type,
                datetime.fromisoformat(last_export_timestamp),
                options,
            )
        else:
            export_records_in_batches(r, record_type, options)

        # Store the timestamp of the last successful bulk import for this
        # record type, expiring after 45 days.
        r.set(last_export_key, str(timezone.now()), 60 * 60 * 24 * 45)
