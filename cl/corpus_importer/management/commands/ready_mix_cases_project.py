import json
import os
import time
from datetime import date
from typing import List, TypedDict

from django.conf import settings
from django.core.management import CommandParser  # type: ignore
from redis import Redis
from redis.exceptions import ConnectionError

from cl.corpus_importer.tasks import make_docket_by_iquery
from cl.lib.argparse_types import valid_date_time
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.elasticsearch_utils import build_es_base_query
from cl.lib.redis_utils import get_redis_interface
from cl.search.documents import DocketDocument
from cl.search.management.commands.cl_index_parent_and_child_docs import (
    log_last_document_indexed,
)
from cl.search.models import SEARCH_TYPES, Court, Docket
from cl.search.tasks import index_dockets_in_bulk


class OptionsType(TypedDict):
    queue: str
    courts: List[str]
    court_type: str
    iterations: int
    iteration_delay: float
    stop_threshold: int
    date_filed: date


def confirm_es_indexing(options):
    queue = options["queue"]
    chunk_size = options["chunk_size"]
    pk_offset = options["pk_offset"]
    chunk = []
    processed_count = 0
    court_ids = get_bankruptcy_courts(["all"])
    dockets = (
        Docket.objects.filter(
            pk__gte=pk_offset,
            court__in=court_ids,
            date_filed__gt=date(2020, 1, 1),
        )
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    count = dockets.count()
    throttle = CeleryThrottle(queue_name=queue)
    for d_id in dockets.iterator():
        processed_count += 1
        last_item = count == processed_count
        chunk.append(d_id)
        if processed_count % chunk_size == 0 or last_item:
            throttle.maybe_wait()
            index_dockets_in_bulk.si(
                chunk,
            ).set(queue=queue).apply_async()
            chunk = []
            logger.info(
                "\rProcessed {}/{}, ({:.0%}) Dockets, last PK indexed: {},".format(
                    processed_count,
                    count,
                    processed_count * 1.0 / count,
                    d_id,
                )
            )
        if not processed_count % 1000:
            # Log every 1000 dockets indexed.
            log_last_document_indexed(d_id, "es_bankr_indexing:log")
    logger.info(f"Successfully indexed {processed_count} dockets.")


def get_bankruptcy_courts(court_ids: list[str]) -> list[str]:
    """Retrieve a list of bankruptcy courts IDS from database.

    :param court_ids: A list of court ids or all.
    :return: A list of Court IDs.
    """
    bankr_courts = (
        Court.federal_courts.bankruptcy_pacer_courts().all().only("pk")
    )
    if court_ids != ["all"]:
        bankr_courts = bankr_courts.filter(pk__in=court_ids)

    return list(bankr_courts.values_list("pk", flat=True))


def get_district_courts(court_ids: list[str]) -> list[str]:
    """Retrieve a list of district courts IDS from database.

    :param court_ids: A list of court ids or all.
    :return: A list of Court IDs.
    """
    district_courts = Court.federal_courts.district_courts().all().only("pk")
    if court_ids != ["all"]:
        district_courts = district_courts.filter(pk__in=court_ids)

    return list(district_courts.values_list("pk", flat=True))


def get_courts_to_scrape(court_type: str, court_ids: list[str]) -> list[str]:
    """Retrieve a list of district,  bankruptcy or all courts IDS
    (district + bankruptcy)  from database.

    :param court_type: The court type.
    :param court_ids: A list of court ids or all.
    :return: A list of Court IDs.
    """

    court_ids_to_scrape = (
        get_bankruptcy_courts(court_ids) + get_district_courts(court_ids)
        if court_type == "all"
        else (
            get_district_courts(court_ids)
            if court_type == "district"
            else (
                get_bankruptcy_courts(court_ids)
                if court_type == "bankruptcy"
                else []
            )
        )
    )
    return court_ids_to_scrape


def get_latest_pacer_case_id(court_id: str, date_filed: date) -> str | None:
    """Fetch the latest pacer_case_id for a specific court and date_filed.

    :param court_id: The court ID.
    :param date_filed: The date_filed for which to find the latest pacer_case_id.
    :return: The latest pacer_case_id if found, otherwise None.
    """

    latest_docket = (
        Docket.objects.filter(
            court_id=court_id,
            date_filed__lte=date_filed,
            pacer_case_id__isnull=False,
        )
        .only("date_filed", "pacer_case_id", "court_id")
        .order_by("-date_filed")
        .first()
    )

    if latest_docket:
        return latest_docket.pacer_case_id
    return None


def get_and_store_starting_case_ids(options: OptionsType, r: Redis) -> None:
    """Get the starting pacer_case_id based on the provided date_filed and
    store it in Redis for each court.

    :param options: The options from the handle method
    :param r: The Redis DB to connect to as a connection interface or str that
    can be handed off to get_redis_interface.
    :return None
    """

    court_ids = get_courts_to_scrape(options["court_type"], options["courts"])
    for court_id in court_ids:
        latest_pacer_case_id = get_latest_pacer_case_id(
            court_id, options["date_filed"]
        )
        if not latest_pacer_case_id:
            r.hdel("iquery_status", court_id)
            continue
        r.hset("iquery_status", court_id, latest_pacer_case_id)
    logger.info("Finished setting starting pacer_case_ids.")


def query_results_in_es(options):
    """Query results in ES.
    :param options: The options from the handle method
    :return None
    """

    court_ids = get_bankruptcy_courts(["all"])
    # The params to perform the query.
    cd = {
        "type": SEARCH_TYPES.RECAP,
        "q": "chapter:7",
        "court": " ".join(court_ids),
        "case_name": "ready mix",
        "filed_after": date(2020, 1, 1),
    }

    search_query = DocketDocument.search()
    s, _ = build_es_base_query(search_query, cd)
    s = s.extra(size=options["results_size"])
    response = s.execute().to_dict()
    extracted_data = [
        {
            "docket_absolute_url": item["_source"]["docket_absolute_url"],
            "dateFiled": item["_source"]["dateFiled"],
            "caseName": item["_source"]["caseName"],
            "docketNumber": item["_source"]["docketNumber"],
            "court_exact": item["_source"]["court_exact"],
            "chapter": item["_source"]["chapter"],
        }
        for item in response["hits"]["hits"]
    ]

    # Save the json results file to: "ready_mix_cases/extracted_ready_mix_cases.json"
    json_path = os.path.join(settings.MEDIA_ROOT, "ready_mix_cases")
    if not os.path.exists(json_path):
        os.makedirs(json_path)

    json_file = os.path.join(
        settings.MEDIA_ROOT,
        "ready_mix_cases",
        "extracted_ready_mix_cases.json",
    )
    with open(json_file, "w", encoding="utf-8") as file:
        json.dump(
            extracted_data,
            file,
            indent=2,
            sort_keys=True,
        )
    logger.info("Finished querying results in ES.")


def add_bank_cases_to_cl(options: OptionsType, r) -> None:
    """Iterate over courts and gather iquery results from them.
    :param options: The options from the handle method
    :param r: The Redis DB to connect to as a connection interface or str that
    can be handed off to get_redis_interface.
    :return None
    """
    q = options["queue"]
    stop_threshold = options["stop_threshold"]
    r = get_redis_interface("CACHE")

    # Only process court with a pacer_case_id from the provided court type.
    court_ids_status = r.hkeys("iquery_status")
    courts_ids_to_scrape = get_courts_to_scrape(
        options["court_type"], options["courts"]
    )
    court_ids = [
        court_id
        for court_id in court_ids_status
        if court_id in courts_ids_to_scrape
    ]

    for court_id in court_ids:
        # Restart empty iquery results to 0.
        r.hset("iquery_empty_results", court_id, 0)

    # Create a queue equal than the number of courts we're doing.
    throttle = CeleryThrottle(queue_name=q, min_items=len(court_ids))
    iterations_completed = 0
    while (
        options["iterations"] == 0
        or iterations_completed < options["iterations"]
    ):
        if len(court_ids) == 0:
            # No more courts. Done!
            logger.info("Finished all courts. Exiting!")
            break

        updated_court_ids = court_ids.copy()
        for court_id in court_ids:
            # Create/update the queue throttle equal than the number of courts
            # we're doing.
            throttle.update_min_items(len(updated_court_ids))
            throttle.maybe_wait()

            iquery_empty_count = int(r.hget("iquery_empty_results", court_id))
            if iquery_empty_count >= stop_threshold:
                # Abort for consecutive empty results.
                # Stop doing this court.
                court_ids.remove(court_id)
                updated_court_ids.remove(court_id)
                continue

            try:
                pacer_case_id = r.hget("iquery_status", court_id)
                if pacer_case_id is None:
                    # Abort, no pacer_case_id found for the given date_filed
                    court_ids.remove(court_id)
                    logger.info(
                        f"Aborting court: {court_id}, no pacer_case_id "
                        f"found in {options['date_filed']}"
                    )
                    continue

                if iquery_empty_count >= stop_threshold:
                    # Abort for consecutive empty results.
                    # Stop doing this court.
                    court_ids.remove(court_id)
                    continue
                pacer_case_id = r.hincrby("iquery_status", court_id, 1)

                if Docket.objects.filter(
                    court_id=court_id, pacer_case_id=str(pacer_case_id)
                ).exists():
                    # Check if we already have the docket. If so, omit it.
                    continue

                make_docket_by_iquery.apply_async(
                    args=(court_id, pacer_case_id),
                    kwargs={"log_results_redis": True},
                    queue=q,
                )
                logger.info(
                    f"Enqueued task for: {pacer_case_id} from {court_id}"
                )
            except ConnectionError:
                logger.info(
                    "Failed to connect to redis. Waiting a bit and making "
                    "a new connection."
                )
                time.sleep(10)
                r = get_redis_interface("CACHE")
                # Continuing here will skip this court for this iteration; not
                # a huge deal.
                continue
            except Exception as e:
                # Cleanup
                r.hincrby("iquery_status", court_id, -1)
                raise e

        iterations_completed += 1
        remaining_iterations = options["iterations"] - iterations_completed
        if remaining_iterations > 0:
            time.sleep(options["iteration_delay"])


class Command(VerboseCommand):
    help = "Scrape bankruptcy iquery pages sequentially."

    def add_arguments(self, parser: CommandParser):
        parser.add_argument(
            "--queue",
            default="batch2",
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--court-type",
            type=str,
            required=True,
            choices=["district", "bankruptcy", "all"],
            help="The court type to scrape, 'district', 'bankruptcy' or 'all'.",
        )
        parser.add_argument(
            "--courts",
            type=str,
            default=["all"],
            nargs="*",
            help="The courts that you wish to parse.",
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=0,
            help="The number of iterations to take. Default is 0, which means "
            "to loop forever",
        )
        parser.add_argument(
            "--iteration-delay",
            type=float,
            default=1.0,
            help="How long to wait after completing an iteration of all "
            "courts before beginning another iteration",
        )
        parser.add_argument(
            "--task",
            type=str,
            choices=[
                "scrape-iquery",
                "set-case-ids",
                "query-results",
                "re-index-dockets",
            ],
            help="Which task do you want to do?",
        )
        parser.add_argument(
            "--stop-threshold",
            type=int,
            default=5,
            help="How many empty iquery pages results before stopping the court.",
        )
        parser.add_argument(
            "--date-filed",
            default="2021-01-18",
            type=valid_date_time,
            help="The date_filed to extract the latest case from.",
        )
        parser.add_argument(
            "--results-size",
            type=int,
            default=1000,
            help="The number of results to retrieve from the ES query.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default="100",
            help="The number of items to index in a single celery task.",
        )
        parser.add_argument(
            "--pk-offset",
            type=int,
            default=0,
            help="The parent document pk to start indexing from.",
        )

    def handle(self, *args, **options):
        r = get_redis_interface("CACHE")
        if options["task"] == "scrape-iquery":
            add_bank_cases_to_cl(options, r)

        if options["task"] == "set-case-ids":
            get_and_store_starting_case_ids(options, r)

        if options["task"] == "query-results":
            query_results_in_es(options)

        if options["task"] == "re-index-dockets":
            confirm_es_indexing(options)
