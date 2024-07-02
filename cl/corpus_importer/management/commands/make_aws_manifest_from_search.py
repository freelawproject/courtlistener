import csv
import io
from typing import Any

import boto3
from django.core.management import CommandParser  # type: ignore
from django_elasticsearch_dsl.search import Search
from elasticsearch_dsl import Q

from cl.lib.command_utils import VerboseCommand
from cl.lib.elasticsearch_utils import (
    add_fields_boosting,
    build_fulltext_query,
    build_sort_results,
)
from cl.search.constants import SEARCH_OPINION_QUERY_FIELDS
from cl.search.documents import OpinionDocument
from cl.search.models import SEARCH_TYPES

s3_client = boto3.client("s3")


def build_base_query(options: dict[str, Any]) -> Search:
    """
    Constructs a base Full text Elasticsearch query using the provided options.

    Args:
        options (dict[str, Any]): A dictionary containing search options:
            - search_text (str): The text to search for.
            - search_type (str): The type of search.
            - es_page_size (int): The desired number of results per page.

    Returns:
        Search: The constructed Elasticsearch query object.

    Raises:
        NotImplementedError: If the provided search_type is not supported.
    """
    cd = {
        "q": options["search_text"],
        "type": options["search_type"],
    }
    match options["search_type"]:
        case SEARCH_TYPES.OPINION:
            unique_sorting_key = "id"
            cd["order_by"] = "score desc"
            search_query = OpinionDocument.search()
            search_fields = SEARCH_OPINION_QUERY_FIELDS.copy()
            search_fields.extend(["type", "text", "caseName", "docketNumber"])
            q_should = build_fulltext_query(
                search_fields, cd["q"], only_queries=True
            )
            query = Q(
                "bool",
                should=q_should,
                filter=Q("match", cluster_child="opinion"),
                minimum_should_match=1,
            )
        case _:
            raise NotImplemented

    search_query = search_query.query(query)
    # Limit the search response to only include the "id" field for each
    # document. This reduces the amount of data transferred and improves
    # performance.
    search_query = search_query.source(includes=["id"])
    # Set the number of results to return per page (`options["es_page_size"]`).
    # We add 1 to this value to enable pagination detection. This extra result
    # allows us to determine if there are more pages available after the
    # current set of results.
    search_query = search_query.extra(size=options["es_page_size"] + 1)
    # Build the sorting settings for an ES query to work with the
    # 'search_after' pagination
    default_sorting = build_sort_results(cd, False, "v4")
    unique_sorting = build_sort_results(
        {"type": cd["type"], "order_by": f"{unique_sorting_key} desc"},
        False,
        "v4",
    )
    search_query = search_query.sort(default_sorting, unique_sorting)
    return search_query


class Command(VerboseCommand):
    help = (
        "Retrieves data records from Elasticsearch and creates manifest files"
        "listing those records in Amazon S3. These manifest files can then"
        "be used by batch processing jobs to efficiently process the data in"
        "parallel."
    )

    def add_arguments(self, parser: CommandParser):
        parser.add_argument(
            "--bucket-name",
            help="The name of the bucket to store documents.",
            required=True,
        )
        parser.add_argument(
            "--search-text",
            type=str,
            required=True,
            help="Query string used to filter the data records to be retrieved",
        )
        parser.add_argument(
            "--search-type",
            type=str,
            required=True,
            choices=[
                SEARCH_TYPES.OPINION,
            ],
            help=f"The search type to import: ({', '.join([SEARCH_TYPES.OPINION])})",
        )
        parser.add_argument(
            "--es-page-size",
            type=int,
            default=100,
            help="The number of records to query in a single ES page.",
        )

    def handle(self, *args, **options):
        bucket_name = options["bucket_name"]
        record_type = options["search_type"]
        search_query = build_base_query(options)
        has_next = True
        search_after = None
        with io.StringIO() as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=["bucket", "file_name"],
                extrasaction="ignore",
            )
            while has_next:
                if search_after:
                    search_query = search_query.extra(
                        search_after=search_after
                    )
                results = search_query.execute()
                # This step ensures we only process the exact number of
                # documents per page defined when calling the command,
                # effectively removing the extra document originally included
                # to check for the existence of a next page.
                clean_page_data = results.hits[: options["es_page_size"]]

                # Create an underscore-separated file name that lambda
                # can split and use as part of batch processing.
                ids = [str(r.id) for r in clean_page_data]
                query_dict = {
                    "bucket": bucket_name,
                    "file_name": "_".join(ids),
                }
                writer.writerow(query_dict)

                has_next = len(results) > options["es_page_size"]
                search_after = clean_page_data[-1].meta.sort

            s3_client.put_object(
                Key=f"{record_type}_es_filelist.csv",
                Bucket=bucket_name,
                Body=csvfile.getvalue().encode("utf-8"),
            )
