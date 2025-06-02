import csv
import io
import random
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
    Reimbursement,
    SpouseIncome,
)
from cl.disclosures.models import Position as FDPosition
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
from cl.search.models import SEARCH_TYPES, SOURCES, Opinion

s3_client = boto3.client("s3")

JUDICIAL_POSITIONS: list[str] = [
    key
    for key, value in Position.POSITION_TYPE_GROUPS.items()
    if value == "Judge"
]

ROLE_ARN = "arn:aws:iam::968642441645:role/bulk-customer-data-batch"


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

    if options["all_records"]:
        filter_clause = ""
        params = []

    query = (
        f"{base_query}\n {filter_clause}\n"
        if filter_clause
        else f"{base_query}\n"
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
        params = []

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
) -> tuple[str, dict[str, Any]]:
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
        record_ids (list[tuple[int]]): A list of tuples, where each tuple
            contains at least the record's unique ID
        base_filename (str): The base name for the manifest file in S3.
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
        batch_counter (int, optional): An optional integer to append to the
            filename for distinguishing between multiple manifest files.

    Returns:
        tuple[str, dict[str, Any]]: A tuple containing:
            - The S3 ARN of the newly uploaded manifest file.
            - A dictionary with the uploaded file's ETag and other properties.
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
        arn = f"arn:aws:s3:::{bucket_name}/{name}"
        manifest_data = s3_client.put_object(
            Key=name,
            Bucket=bucket_name,
            Body=csvfile.getvalue().encode("utf-8"),
        )
    return arn, manifest_data


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
            "\rRetrieved %d/%d (%.0f%%), last PK processed: %s",
            record_count + records_processed,
            total_number_of_records,
            (record_count + records_processed)
            * 100.0
            / total_number_of_records,
            last_pk,
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
        timestamp: The datetime object representing the lower bound
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
    record_type: str, timestamp: datetime, all_records: bool = False
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
        all_records: Optional boolean flag. If True, all records of the
            specified `record_type` modified on or after the `timestamp`
            will be returned, bypassing filters.

    Returns:
        A list of unique integer IDs for the records of the specified type
        that were created or modified on or after the given `timestamp`.
    """
    related_field = "pk"
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

    record_ids = get_records_modified_since(main_model, "pk", timestamp)
    # check nested/related models
    for model in nested_models:
        record_ids.extend(
            get_records_modified_since(model, related_field, timestamp)
        )

    match record_type:
        case SEARCH_TYPES.OPINION if not all_records:
            # Apply filters to include only opinions that are either:
            # 1. Not extracted by OCR.
            # 2. Associated with a cluster whose source contains HARVARD_CASELAW
            ids = [x[0] for x in record_ids]
            return list(
                Opinion.objects.filter(pk__in=ids)
                .filter(
                    Q(extracted_by_ocr=False)
                    | Q(cluster__source__icontains=SOURCES.HARVARD_CASELAW)
                )
                .values_list("pk")
                .distinct()
            )
        case SEARCH_TYPES.PEOPLE if not all_records:
            # Filter record IDs for people, including only those who have
            # judicial positions.
            ids = [x[0] for x in record_ids]
            return list(
                Person.objects.filter(pk__in=ids)
                .filter(positions__position_type__in=JUDICIAL_POSITIONS)
                .values_list("pk")
                .distinct()
            )
        case _:
            return list(set(record_ids))


def upload_list_of_records_for_users(
    record_type: str, bucket_name: str, record_ids: list[tuple[int]]
):
    """
    Uploads a CSV file containing record IDs and corresponding S3 keys.

    This CSV file serves as a manifest for users to easily retrieve the new or
    updated records. Each row in the CSV provides the original record ID and
    the S3 key where the corresponding record data can be downloaded.

    Args:
        record_type: The type of records being uploaded. This determines the
            prefix used in the S3 key.
        bucket_name: The name of the S3 bucket where the CSV file will be
            uploaded.
        record_ids: A list of tuples, where each tuple contains a single integer
            representing the ID of a record.

    Raises:
        NotImplementedError: If the provided `record_type` is not supported.
    """
    timestamp = timezone.now()
    filename = (
        f"{record_type}_new_or_updated_{timestamp.month}_{timestamp.year}"
    )
    match record_type:
        case SEARCH_TYPES.OPINION:
            prefix = "ai_case_law_dataset"
        case SEARCH_TYPES.ORAL_ARGUMENT:
            prefix = "ai_audio_dataset"
        case SEARCH_TYPES.PEOPLE:
            prefix = "ai_judges_dataset"
        case "fd":
            prefix = "ai_financial_disclosure_dataset/"
        case _:
            raise NotImplementedError(
                f"Record type '{record_type}' is not supported."
            )

    with io.StringIO() as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["id", "key"],
            extrasaction="ignore",
        )
        for row in record_ids:
            query_dict = {
                "id": row[0],
                "key": f"{prefix}/{record_type}_{row[0]}.json",
            }
            writer.writerow(query_dict)

        s3_client.put_object(
            Key=f"{prefix}/{filename}.csv",
            Bucket=bucket_name,
            Body=csvfile.getvalue().encode("utf-8"),
        )


def get_account_id() -> str:
    """
    Retrieves the AWS account ID of the current execution role.

    :return: The AWS account ID.
    """
    sts_client = boto3.client("sts")
    return sts_client.get_caller_identity().get("Account")


def get_lambda_arns(region_name: str = "us-west-2") -> dict[str, str]:
    """
    Retrieves a dictionary of AWS Lambda function names and their ARNs.
    Args:
        region_name (str): The AWS region (e.g., 'us-east-1', 'eu-west-2')
            from which to retrieve Lambda function information.

    Returns:
        A dictionary where keys are Lambda function names (str) and values
        are their corresponding ARNs (str).
    """
    lambda_client = boto3.client("lambda", region_name=region_name)
    paginator = lambda_client.get_paginator("list_functions")
    lambda_arns = {}
    for page in paginator.paginate():
        for function in page.get("Functions", []):
            lambda_arns[function["FunctionName"]] = function["FunctionArn"]

    return lambda_arns


def create_and_execute_batch_job(
    record_type: str,
    bucket_name: str,
    region_name: str,
    manifest_arn: str,
    manifest_etag: str,
) -> None:
    """
    Creates and executes an S3 Batch Operations job to process records of a
    specific type.

    This function dynamically selects the appropriate AWS Lambda function based
    on the `record_type` and then creates an S3 Batch Operations job. The job
    is configured to invoke the chosen Lambda function for each object listed
    in the provided S3 manifest.

    Args:
        record_type (str): The type of record to process.
        bucket_name (str): The name of the bucket.
        region_name (str): The AWS region where the S3 Batch Operations job
            will be created and executed.
        manifest_arn (str): ARN of the S3 manifest file.
        manifest_etag (str): The ETag of the manifest file

    """
    match record_type:
        case SEARCH_TYPES.OPINION:
            lambda_name = "case_law_bulk_export"
        case SEARCH_TYPES.ORAL_ARGUMENT:
            lambda_name = "oral_argument_bulk_export"
        case SEARCH_TYPES.PEOPLE:
            lambda_name = "judges_bulk_export"
        case "fd":
            lambda_name = "financial_disclosure_bulk_export"
        case _:
            raise NotImplementedError(
                f"Record type '{record_type}' is not supported."
            )

    account_id = get_account_id()
    lambda_arns_dict = get_lambda_arns(region_name)
    s3_control = boto3.client("s3control", region_name=region_name)
    s3_control.create_job(
        AccountId=account_id,
        ConfirmationRequired=False,
        Operation={
            "LambdaInvoke": {
                "FunctionArn": lambda_arns_dict[lambda_name],
                "InvocationSchemaVersion": "2.0",
            },
        },
        Report={
            "Bucket": f"arn:aws:s3:::{bucket_name}",
            "Format": "Report_CSV_20180820",
            "Enabled": True,
            "ReportScope": "AllTasks",
        },
        Manifest={
            "Spec": {
                "Format": "S3BatchOperations_CSV_20180820",
                "Fields": ["Bucket", "Key"],
            },
            "Location": {
                "ObjectArn": manifest_arn,
                "ETag": manifest_etag,
            },
        },
        Priority=random.randint(0, 10),
        RoleArn=ROLE_ARN,
    )


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
        timestamp: A datetime object representing the month for which
            to generate the export. The filename will be based on this
            timestamp.
        options: A dictionary containing options to be passed to the
            `upload_manifest` function.
    """
    current_timestamp = timezone.now()
    filename = f"{record_type}_monthly_export_{current_timestamp.month}_{current_timestamp.year}"
    record_ids = get_monthly_record_ids_by_type(
        record_type, timestamp, all_records=options["all_records"]
    )
    arn, manifest_data = upload_manifest(record_ids, filename, options)
    upload_list_of_records_for_users(
        record_type, options["bucket_name"], record_ids
    )
    create_and_execute_batch_job(
        record_type,
        options["bucket_name"],
        options["region_name"],
        arn,
        manifest_data["ETag"],
    )


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
            "--region-name",
            type=str,
            help="The AWS region where the S3 bucket is located.",
            default="us-west-2",
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
        last_export_key = f"bulk_import:{record_type}"

        if monthly_export:
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
