# Import the troller BK RSS feeds
import argparse
import concurrent.futures
import linecache
import re
import threading
from datetime import datetime
from queue import Queue
from typing import Any, Mapping, TypedDict
from urllib.parse import unquote

from django.db import DataError, IntegrityError, transaction
from django.utils.timezone import make_aware, utc
from juriscraper.pacer import PacerRssFeed

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer import map_pacer_to_cl_id
from cl.lib.redis_utils import make_redis_interface
from cl.lib.storage import S3PrivateUUIDStorage
from cl.recap.mergers import (
    add_bankruptcy_data_to_docket,
    add_docket_entries,
    find_docket_object,
    update_docket_metadata,
)
from cl.recap_rss.tasks import (
    cache_hash,
    get_last_build_date,
    hash_item,
    is_cached,
)
from cl.search.models import Court
from cl.search.tasks import add_items_to_solr

FILES_BUFFER_THRESHOLD = 3


def merge_rss_data(
    feed_data: list[dict[str, Any]],
    court_id: str,
    build_date: datetime | None,
) -> tuple[list[int], int]:
    """Merge the RSS data into the database

    :param feed_data: Data from an RSS feed file
    :param court_id: The PACER court ID for the item
    :param build_date: The RSS date build.
    :return: A list of RECAPDocument PKs that can be passed to Solr
    """

    court_id = map_pacer_to_cl_id(court_id)
    dockets_created = 0
    all_rds_created: list[int] = []
    district_court_ids = (
        Court.federal_courts.district_pacer_courts().values_list(
            "pk", flat=True
        )
    )
    courts_exceptions_no_rss = ["miwb", "nceb", "pamd", "cit"]
    if (
        build_date
        and build_date > make_aware(datetime(year=2018, month=4, day=20), utc)
        and court_id in district_court_ids
        and court_id not in courts_exceptions_no_rss
    ):
        # Avoid parsing/adding feeds after we start scraping RSS Feeds for
        # district and bankruptcy courts.
        return all_rds_created, dockets_created
    for docket in feed_data:
        item_hash = hash_item(docket)
        if is_cached(item_hash):
            logger.info(
                f"Hit a cached item, finished adding {court_id} feed. "
                f"Added {len(all_rds_created)} RDs."
            )
            return all_rds_created, dockets_created

        if (
            not docket["pacer_case_id"]
            and not docket["docket_number"]
            or not len(docket["docket_entries"])
        ):
            continue

        with transaction.atomic():
            cached_ok = cache_hash(item_hash)
            if not cached_ok:
                # The item is already in the cache, ergo it's getting processed
                # in another thread/process and we had a race condition.
                continue

            d = find_docket_object(
                court_id,
                docket["pacer_case_id"],
                docket["docket_number"],
            )
            document_number = docket["docket_entries"][0]["document_number"]
            if (
                document_number
                and d.docket_entries.filter(
                    entry_number=document_number
                ).exists()
            ):
                # It's an existing docket entry; let's not add it.
                continue
            if not d.pk:
                update_docket_metadata(d, docket)
                dockets_created += 1

            if not d.pacer_case_id:
                d.pacer_case_id = docket["pacer_case_id"]
            try:
                d.save()
                add_bankruptcy_data_to_docket(d, docket)
            except (DataError, IntegrityError) as exc:
                # Trouble. Log and move on
                logger.warn(
                    f"Got DataError or IntegrityError while saving docket."
                )

            des_returned, rds_created, content_updated = add_docket_entries(
                d,
                docket["docket_entries"],
                do_not_update_existing=True,
            )
            if content_updated:
                # Only add recap source if a docket entry was created.
                d.add_recap_source()
                try:
                    d.save()
                except IntegrityError as exc:
                    # Trouble. Log and move on
                    logger.warn(f"Got IntegrityError while saving docket.")

        all_rds_created.extend([rd.pk for rd in rds_created])

    logger.info(
        f"Finished adding {court_id} feed. Added {len(all_rds_created)} RDs."
    )
    return all_rds_created, dockets_created


def parse_file(
    binary_content: bytes,
    court_id: str,
) -> tuple[Any, datetime | None]:
    """Parse a RSS file and return the data.

    :param binary_content: The binary content of the file to parse.
    :param court_id: The PACER court ID for the item
    :return The parsed data from the retrieved XML feed.
    """

    feed = PacerRssFeed(court_id)
    content = binary_content.decode("utf-8")
    feed._parse_text(content)
    build_date = get_last_build_date(binary_content)
    return feed.data, build_date


def get_court_from_line(line: str):
    """Get the court_id from the line.

    This is a bit annoying. Each file name looks something like:

        sources/troller-files/o-894|1599853056
        sources/troller-files/w-w-894|1599853056
        sources/troller-files/o-DCCF0395-BDBA-C444-149D8D8EFA2EC03D|1576082101
        sources/troller-files/w-88AC552F-BDBA-C444-1BD52598BA252265|1435103773
        sources/troller-files/w-w-DCCF049E-BDBA-C444-107C577164350B1E|1638858935
        sources/troller-files/w-88AC552F-BDBA-C444-1BD52598BA252265-1399913581
        sources/troller-files/w-w-Mariana|1638779760

    The court_id is based on the part between the "/o-" and the "|" or "-".
    Match it, look it up in our table of court IDs, and return the correct PACER ID.

    :param line: A line to a file in S3
    :return: The PACER court ID for the feed
    """

    court = None
    regex = re.compile(
        r"([A-Z0-9]{8}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{16})|-([0-9]{3})\||-([0-9]{3})-|(Mariana)"
    )
    match = re.search(regex, line)
    if match is None:
        return None
    if match.group(1):
        court = match.group(1)
    if match.group(2):
        court = match.group(2)
    if match.group(3):
        court = match.group(3)
    if match.group(4):
        court = match.group(4)

    if not court:
        return None
    return troller_ids.get(court, None)


class OptionsType(TypedDict):
    offset: int
    limit: int
    file: str


def log_added_items_to_redis(
    dockets_created: int, rds_created: int, line: int
) -> Mapping[str | bytes, int | str]:
    """Log the number of dockets and recap documents created to redis.
    Get the previous stored values and add the new ones.

    :param dockets_created: The dockets created.
    :param rds_created: The recap documents created.
    :param line: The last line imported.
    :return: The data logged to redis.
    """

    r = make_redis_interface("STATS")
    pipe = r.pipeline()
    log_key = "troller_bk:log"
    pipe.hgetall(log_key)
    stored_values = pipe.execute()
    current_total_dockets = int(stored_values[0].get("total_dockets", 0))
    current_total_rds = int(stored_values[0].get("total_rds", 0))

    total_dockets_created = dockets_created + current_total_dockets
    total_rds_created = rds_created + current_total_rds
    log_info: Mapping[str | bytes, int | str] = {
        "total_dockets": total_dockets_created,
        "total_rds": total_rds_created,
        "last_line": line,
        "date_time": datetime.now().isoformat(),
    }
    pipe.hset(log_key, mapping=log_info)
    pipe.expire(log_key, 60 * 60 * 24 * 28)  # 4 weeks
    pipe.execute()
    return log_info


def download_file(item_path: str, order: int) -> tuple[bytes, str, int]:
    """Small wrapper to download and read a file from S3.
    :param item_path: The file path to download.
    :param order: The original order of the file to keep in the queue.
    :return: A tuple of the binary content of the file, the file path and the
    file order.
    """
    bucket = S3PrivateUUIDStorage()
    with bucket.open(item_path, mode="rb") as f:
        binary_content = f.read()
    return binary_content, item_path, order


def download_files_from_paths(
    item_paths: list[str], files_queue: Queue
) -> None:
    """Download multiple files concurrently and store them to a Queue.
    :param item_paths: The list of file paths to download.
    :param files_queue: The Queue where store the downloaded files.
    :return: None
    """

    order = 0
    with concurrent.futures.ThreadPoolExecutor() as executor:
        concurrent_downloads = []
        for item_path in item_paths:
            concurrent_downloads.append(
                executor.submit(download_file, item_path, order)
            )
            order += 1

        # Wait for all the downloads to complete.
        completed_downloads = concurrent.futures.as_completed(
            concurrent_downloads
        )
        # Order the downloads to preserver their original chron order.
        completed_and_ordered = sorted(
            list(completed_downloads), key=lambda a: a.result()[2]
        )
        # Add files to the Queue
        for download in completed_and_ordered:
            files_queue.put(download.result())


def download_files_concurrently(
    files_queue: Queue,
    file_path: str,
    files_downloaded_offset: int,
    threads: list[threading.Thread],
) -> int:
    """Get the next files to download and start a thread to download them.
    :param files_queue: The Queue where store the downloaded files.
    :param file_path: The file containing the list of paths to download.
    :param files_downloaded_offset: The files that have been already downloaded
    :param threads: The list of threads.
    :return: The files_downloaded_offset updated
    """

    files_to_download = []
    linecache.clearcache()
    linecache.checkcache(file_path)
    if files_queue.qsize() < FILES_BUFFER_THRESHOLD:
        for j in range(FILES_BUFFER_THRESHOLD):
            # Get the next paths to download.
            next_line = linecache.getline(
                file_path, files_downloaded_offset + 1
            )
            if next_line:
                files_to_download.append(unquote(next_line).replace("\n", ""))
                files_downloaded_offset += 1

        # Download the files concurrently.
        download_thread = threading.Thread(
            target=download_files_from_paths,
            args=(files_to_download, files_queue),
        )
        download_thread.start()
        threads.append(download_thread)

    return files_downloaded_offset


def iterate_and_import_files(options: OptionsType) -> None:
    """Iterate over the inventory file and import all new items.

     - Merge into the DB
     - Add to solr
     - Do not send alerts or webhooks
     - Do not touch dockets with entries (troller data is old)
     - Do not parse (add) district/bankruptcy courts feeds after 2018-4-20
     that is the RSS feeds started being scraped by RECAP.

    :param options: The command line options
    :return: None
    """

    f = open(options["file"], "r", encoding="utf-8")
    total_dockets_created = 0
    total_rds_created = 0

    files_queue = Queue()
    threads = []

    files_downloaded_offset = options["offset"]
    for i, line in enumerate(f):
        if i < options["offset"]:
            continue
        if i >= options["limit"] > 0:
            break

        # If the files_queue has less than FILES_BUFFER_THRESHOLD files, then
        # download more files ahead and store them to the queue.
        files_downloaded_offset = download_files_concurrently(
            files_queue, f.name, files_downloaded_offset, threads
        )

        # If the files_queue gets empty, wait for it to refill until there are
        # at least FILES_BUFFER_THRESHOLD files in the queue.
        if files_queue.qsize() == 0:
            while True:
                if files_queue.qsize() >= FILES_BUFFER_THRESHOLD:
                    break

        # Process a file from the queue.
        binary, item_path, order = files_queue.get()
        court_id = get_court_from_line(item_path)
        logger.info(f"Attempting: {item_path=} with {court_id=} \n")
        if not court_id:
            # Probably a court we don't know
            continue

        feed_data, build_date = parse_file(binary, court_id)
        rds_for_solr, dockets_created = merge_rss_data(
            feed_data, court_id, build_date
        )
        add_items_to_solr.delay(rds_for_solr, "search.RECAPDocument")

        total_dockets_created += dockets_created
        total_rds_created += len(rds_for_solr)

        # Mark the file as completed and remove it from the queue.
        files_queue.task_done()

        # Remove completed download threads from the list of threads.
        for thread in threads:
            if not thread.is_alive():
                threads.remove(thread)

        logger.info(f"Last line imported: {i} \n")

        if not i % 25:
            # Log every 25 lines.
            log_added_items_to_redis(
                total_dockets_created, total_rds_created, i
            )
            # Restart counters after logging into redis.
            total_dockets_created = 0
            total_rds_created = 0

    f.close()


class Command(VerboseCommand):
    help = "Import the troller BK RSS files from S3 to the DB"

    def add_arguments(self, parser):
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="The number of items to skip before beginning. Default is to "
            "skip none.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="After doing this number, stop. This number is not additive "
            "with the offset parameter. Default is to do all of them.",
        )
        parser.add_argument(
            "--file",
            type=str,
            help="Where is the text file that has the list of paths from the "
            "bucket? Create this from an S3 inventory file, by removing "
            "all but the path column",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        if not options["file"]:
            raise argparse.ArgumentError(
                "The 'file' argument is required for that action."
            )

        iterate_and_import_files(options)


troller_ids = {
    "88AC552F-BDBA-C444-1BD52598BA252265": "nmb",
    "DCCF0395-BDBA-C444-149D8D8EFA2EC03D": "almb",
    "DCCF03A4-BDBA-C444-13AFEC481CF81C91": "alnb",
    "DCCF03B4-BDBA-C444-180877EB555CF90A": "alsb",
    "DCCF03C3-BDBA-C444-10B70B118120A4F8": "akb",
    "DCCF03D3-BDBA-C444-1EA2D2D99D26D437": "azb",
    "DCCF03E3-BDBA-C444-11C3D8B9C688D49E": "areb",
    "DCCF03F2-BDBA-C444-14974FDC2C6DD113": "arwb",
    "DCCF0412-BDBA-C444-1C60416590832545": "cacb",
    "DCCF0421-BDBA-C444-12F451A14D4239AC": "caeb",
    "DCCF0431-BDBA-C444-1CE9AB1898357D63": "canb",
    "DCCF0440-BDBA-C444-1C8FEECE5B5AD482": "casb",
    "DCCF0460-BDBA-C444-1282B46DCB6DF058": "cob",
    "DCCF046F-BDBA-C444-126D999DD997D9A5": "ctb",
    "DCCF047F-BDBA-C444-16EA4D3A7417C840": "deb",
    "DCCF048F-BDBA-C444-12505144CA111B75": "dcb",
    "DCCF049E-BDBA-C444-107C577164350B1E": "flmb",
    "DCCF04BD-BDBA-C444-17B566BCA4E30864": "flnb",
    "DCCF04CD-BDBA-C444-13315D191ADF5852": "flsb",
    "DCCF04DD-BDBA-C444-11B09E58A8308286": "gamb",
    "DCCF04EC-BDBA-C444-113648D978F0FF3B": "ganb",
    "DCCF04FC-BDBA-C444-167F8376D8DF181B": "gasb",
    "DCCF050C-BDBA-C444-1191B98D5C279255": "gub",
    "DCCF051B-BDBA-C444-10E608B4E279AE73": "hib",
    "DCCF052B-BDBA-C444-1128ADF2BE776FF5": "idb",
    "DCCF053A-BDBA-C444-1E17C5EDDAAA98B3": "ilcb",
    "DCCF055A-BDBA-C444-1B33BEAA267C9EF3": "ilnb",
    "DCCF0569-BDBA-C444-10AAC89D6254827B": "ilsb",
    "DCCF0579-BDBA-C444-13FDD2CBFCA0428E": "innb",
    "DCCF0589-BDBA-C444-1403298F660F3248": "insb",
    "DCCF0598-BDBA-C444-1D4AA3760C808AC6": "ianb",
    "DCCF05A8-BDBA-C444-147676B19FFD9A64": "iasb",
    "DCCF05B7-BDBA-C444-1159BABEABFF7AD8": "ksb",
    "DCCF05C7-BDBA-C444-181132DD188F5B98": "kyeb",
    "DCCF05D7-BDBA-C444-173EA852DA3C02F3": "kywb",
    "DCCF05E6-BDBA-C444-1BBCF61EC04D7339": "laeb",
    "DCCF05F6-BDBA-C444-1CC8B0B3A0BA9BBE": "lamb",
    "DCCF0606-BDBA-C444-156EC6BFC06D300C": "lawb",
    "DCCF0615-BDBA-C444-12DA3916397575D1": "meb",
    "DCCF0625-BDBA-C444-16B46E54DD6D2B3F": "mdb",
    "DCCF0634-BDBA-C444-172D1B61491F44EB": "mab",
    "DCCF0644-BDBA-C444-16D30512F57AD7E7": "mieb",
    "DCCF0654-BDBA-C444-1B26AFB780F7E57D": "miwb",
    "DCCF0663-BDBA-C444-1E2D50E14B7E69B6": "mnb",
    "DCCF0673-BDBA-C444-162C60670DF8F3CC": "msnb",
    "DCCF0683-BDBA-C444-16D08467B7FFD39C": "mssb",
    "DCCF0692-BDBA-C444-105A607741D9B25E": "moeb",
    "DCCF06B1-BDBA-C444-1D0081621397B587": "mowb",
    "DCCF06C1-BDBA-C444-116BC0B37A3105FA": "mtb",
    "DCCF06D1-BDBA-C444-16605BEF7E402AFF": "neb",
    "DCCF06E0-BDBA-C444-142566FBDE706DF9": "nvb",
    "DCCF06F0-BDBA-C444-15CEC5BC7E8811B0": "nhb",
    "DCCF0700-BDBA-C444-1833C704F349B4C5": "njb",
    "DCCF071F-BDBA-C444-12E80A7584DAB242": "nyeb",
    "DCCF072E-BDBA-C444-161CCB961DC28EAA": "nynb",
    "DCCF073E-BDBA-C444-195A319E0477A40F": "nysb",
    "DCCF075D-BDBA-C444-1A4574BEA4332780": "nywb",
    "DCCF076D-BDBA-C444-1D86BA6110EAC8EB": "nceb",
    "DCCF077D-BDBA-C444-19E00357E47293C6": "ncmb",
    "DCCF078C-BDBA-C444-13A763C27712238D": "ncwb",
    "DCCF079C-BDBA-C444-152775C142804DBF": "ndb",
    "DCCF07AB-BDBA-C444-1909DD6A1D03789A": "ohnb",
    "DCCF07BB-BDBA-C444-15CC4C79DA8F0883": "ohsb",
    "DCCF07CB-BDBA-C444-16A03EA3C59A0E65": "okeb",
    "DCCF07DA-BDBA-C444-19C1613A6E47E8CC": "oknb",
    "DCCF07EA-BDBA-C444-11A55B458254CDA2": "okwb",
    "DCCF07FA-BDBA-C444-1931F6C553EEC927": "orb",
    "DCCF0819-BDBA-C444-121A57E62D0F901B": "paeb",
    "DCCF0838-BDBA-C444-11578199813DA094": "pamb",
    "DCCF0848-BDBA-C444-1FDC44C3E5C7F028": "pawb",
    "DCCF0857-BDBA-C444-1249D33530373C4A": "prb",
    "DCCF0867-BDBA-C444-11F248F5A172BED7": "rib",
    "DCCF0877-BDBA-C444-140D6F0E2517D28A": "scb",
    "DCCF0886-BDBA-C444-1FA114144D695156": "sdb",
    "DCCF0896-BDBA-C444-19AE23DDBC293010": "tneb",
    "DCCF08A5-BDBA-C444-16F88B92DFEFF2D7": "tnmb",
    "DCCF08B5-BDBA-C444-1015B0D4FD4EA2BB": "tnwb",
    "DCCF08D4-BDBA-C444-17A1F7F9130C2B5A": "txeb",
    "DCCF08E4-BDBA-C444-1FF320EDE23FE1C4": "txnb",
    "DCCF08F4-BDBA-C444-137D9095312F2A26": "txsb",
    "DCCF0903-BDBA-C444-1F1B7B299E8BEDEC": "txwb",
    "DCCF0913-BDBA-C444-1426E01E34A098A8": "utb",
    "DCCF0922-BDBA-C444-1E7C4839C9DDE0DD": "vtb",
    "DCCF0932-BDBA-C444-1E3B6019198C4AF3": "vib",
    "DCCF0942-BDBA-C444-15DE36A8BF619EE3": "vaeb",
    "DCCF0951-BDBA-C444-156287CAA9B5EA92": "vawb",
    "DCCF0961-BDBA-C444-113035CFC50A69B8": "waeb",
    "DCCF0971-BDBA-C444-1AE1249D4E72B62E": "wawb",
    "DCCF0980-BDBA-C444-12EE39B96F6E2CAD": "wvnb",
    "DCCF0990-BDBA-C444-16831E0CC62633BB": "wvsb",
    "DCCF099F-BDBA-C444-163A7EEE0EB991F6": "wieb",
    "DCCF09BF-BDBA-C444-1D3842A8131499EF": "wiwb",
    "DCCF09CE-BDBA-C444-1B4915E476D3A9D2": "wyb",
    "Mariana": "nmib",
    "640": "almd",
    "645": "alsd",
    "648": "akd",
    "651": "azd",
    "653": "ared",
    "656": "arwd",
    "659": "cacd",
    "662": "caed",
    "664": "cand",
    "667": "casd",
    "670": "cod",
    "672": "ctd",
    "675": "ded",
    "678": "dcd",
    "681": "flmd",
    "686": "flsd",
    "689": "gamd",
    "696": "gud",
    "699": "hid",
    "701": "idd",
    "704": "ilcd",
    "707": "ilnd",
    "712": "innd",
    "715": "insd",
    "717": "iand",
    "720": "iasd",
    "723": "ksd",
    "728": "kywd",
    "731": "laed",
    "734": "lamd",
    "737": "lawd",
    "740": "med",
    "744": "mad",
    "747": "mied",
    "750": "miwd",
    "757": "mssd",
    "759": "moed",
    "762": "mowd",
    "765": "mtd",
    "768": "ned",
    "771": "nvd",
    "773": "nhd",
    "776": "njd",
    "779": "nmd",
    "781": "nyed",
    "784": "nynd",
    "787": "nysd",
    "792": "nced",
    "795": "ncmd",
    "798": "ncwd",
    "803": "nmid",
    "806": "ohnd",
    "811": "ohsd",
    "818": "okwd",
    "821": "ord",
    "823": "paed",
    "826": "pamd",
    "829": "pawd",
    "832": "prd",
    "835": "rid",
    "840": "sdd",
    "843": "tned",
    "846": "tnmd",
    "849": "tnwd",
    "851": "txed",
    "854": "txnd",
    "856": "txsd",
    "859": "txwd",
    "862": "utd",
    "865": "vtd",
    "868": "vid",
    "873": "vawd",
    "876": "waed",
    "879": "wawd",
    "882": "wvnd",
    "885": "wvsd",
    "888": "wied",
    "891": "wiwd",
    "894": "wyd",
    # Appellate
    "609": "ca6",
    "619": "ca10",
    "625": "cadc",
    "628": "cafc",
    # I don't think we currently crawl these. Worth checking.
    "633": "uscfc",
    "636": "cit",
}
