# Import the troller BK RSS feeds
import argparse
import re
from typing import Any, TypedDict
from urllib.parse import unquote

from django.db import IntegrityError, transaction
from juriscraper.pacer import PacerRssFeed

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer import map_pacer_to_cl_id
from cl.lib.storage import S3PrivateUUIDStorage
from cl.recap.mergers import (
    add_bankruptcy_data_to_docket,
    add_docket_entries,
    find_docket_object,
)
from cl.search.tasks import add_items_to_solr


def merge_rss_data(
    feed_data: list[dict[str, Any]],
    court_id: str,
) -> list[int]:
    """Merge the RSS data into the database

    :param feed_data: Data from an RSS feed file
    :param court_id: The PACER court ID for the item
    :return: A list of RECAPDocument PKs that can be passed to Solr
    """
    all_rds_created = []
    for docket in feed_data:
        if not docket["pacer_case_id"] and docket["docket_number"]:
            continue
        with transaction.atomic():
            d = find_docket_object(
                map_pacer_to_cl_id(court_id),
                docket["pacer_case_id"],
                docket["docket_number"],
            )
            if d.docket_entries.count() > 0:
                # It's an existing docket; let's not update it.
                continue

            d.add_recap_source()
            if not d.pacer_case_id:
                d.pacer_case_id = docket["pacer_case_id"]
            try:
                d.save()
                add_bankruptcy_data_to_docket(d, docket)
            except IntegrityError as exc:
                # Trouble. Log and move on
                logger.warn(f"Got IntegrityError while saving docket.")

            des_returned, rds_created, content_updated = add_docket_entries(
                d, docket["docket_entries"]
            )

        all_rds_created.extend([rd.pk for rd in rds_created])

    logger.info(
        f"Finished adding docket {d}. Added {len(all_rds_created)} RDs."
    )
    return all_rds_created


def download_and_parse(
    item_path: str,
    court_id: str,
) -> list[dict[str, Any]]:
    """Get an item from S3, parse it, and return the data

    :param item_path: The path to the item in the private S3 bucket
    :param court_id: The PACER court ID for the item
    :return The parsed data from the retrieved XML feed.
    """
    bucket = S3PrivateUUIDStorage()
    with bucket.open(item_path, mode="rb") as f:
        feed = PacerRssFeed(court_id)
        feed._parse_text(f.read().decode("utf-8"))
    return feed.data


def get_court_from_line(line: str) -> None | str:
    """Get the court_id from the line.

    This is a bit annoying. Each file name looks something like:

        sources/troller-files/o-894|1599853056
        sources/troller-files/o-DCCF0395-BDBA-C444-149D8D8EFA2EC03D|1576082101

    The court_id is based on the part between the "/o-" and the "|". Match it,
    look it up in our table of court IDs, and return the correct PACER ID.

    :param line: A line to a file in S3
    :return: The PACER court ID for the feed
    """
    try:
        court = m = re.search(r"/o\-(.*)\|", line).group(1)
    except AttributeError:
        # Couldn't find a match
        return None
    return court


class OptionsType(TypedDict):
    offset: int
    limit: int
    file: str


def iterate_and_import_files(options: OptionsType) -> None:
    """Iterate over the inventory file and import all new items.

     - Merge into the DB
     - Add to solr
     - Do not send alerts or webhooks
     - Do not touch dockets with entries (troller data is old)
     - Do not do circuit courts (we're not ready for their feeds)

    :param options: The command line options
    :return: None
    """
    f = open(options["file"], "r")

    for i, line in enumerate(f):
        if i < options["offset"]:
            continue
        if i >= options["limit"]:
            break

        # The first column of the CSV should be a
        item_path = unquote(line)
        court_id = get_court_from_line(line)
        logger.info(f"Attempting: {item_path=} with {court_id=}")
        if not court_id:
            # Probably a court we don't know or a circuit court
            continue

        feed_data = download_and_parse(item_path, court_id)
        rds_for_solr = merge_rss_data(feed_data, court_id)
        add_items_to_solr(rds_for_solr, "search.RECAPDocument")

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
            type=argparse.FileType("r"),
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
    "DCCF0598-BDBA-C444-1D4AA3760C808AC6": "ionb",
    "DCCF05A8-BDBA-C444-147676B19FFD9A64": "iosb",
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
    "653": "aked",
    "656": "akwd",
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
    "717": "iond",
    "720": "iosd",
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
}
