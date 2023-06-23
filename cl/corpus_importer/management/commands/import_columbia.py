import fnmatch
import os
import re
import traceback
from datetime import datetime
from glob import glob
from random import shuffle
from typing import Optional

import dateutil.parser as dparser
from bs4 import BeautifulSoup, NavigableString
from courts_db import find_court
from juriscraper.lib.string_utils import (
    CaseNameTweaker,
    clean_string,
    harmonize,
    titlecase,
)

from cl.corpus_importer.import_columbia.populate_opinions import add_new_case
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.crypto import sha1_of_file
from cl.lib.import_lib import (
    get_courtdates,
    get_min_dates,
    get_min_nocite,
    get_path_list,
)
from cl.people_db.lookup_utils import extract_judge_last_name

# Initialized once since it takes resources
CASE_NAME_TWEAKER = CaseNameTweaker()


def format_case_name(case_name: str) -> str:
    """Applies standard harmonization methods after normalizing with lowercase.
    :param case_name: text to normalize
    :return: normalized text
    """
    return titlecase(harmonize(case_name.lower()))


def parse_dates(
    raw_dates: list[str],
) -> list[list[tuple[Optional[str], datetime]]]:
    """Parses the dates from a list of string.

    Returns a list of lists of (string, datetime) tuples if there is a string
    before the date (or None).

    :param raw_dates: A list of (probably) date-containing strings
    """
    months = re.compile(
        "january|february|march|april|may|june|july|august|"
        "september|october|november|december"
    )
    dates = []
    for raw_date in raw_dates:
        # there can be multiple years in a string, so we split on possible
        # indicators
        raw_parts = re.split(r"(?<=[0-9][0-9][0-9][0-9])(\s|.)", raw_date)

        # index over split line and add dates
        inner_dates = []
        for raw_part in raw_parts:
            # consider any string without either a month or year not a date
            no_month = False
            if re.search(months, raw_part.lower()) is None:
                no_month = True
                if re.search("[0-9][0-9][0-9][0-9]", raw_part) is None:
                    continue
            # strip parenthesis from the raw string (this messes with the date
            # parser)
            raw_part = raw_part.replace("(", "").replace(")", "")
            # try to grab a date from the string using an intelligent library
            try:
                d = dparser.parse(raw_part, fuzzy=True).date()
            except:
                continue

            # split on either the month or the first number (e.g. for a
            # 1/1/2016 date) to get the text before it
            if no_month:
                text = re.compile(r"(\d+)").split(raw_part.lower())[0].strip()
            else:
                text = months.split(raw_part.lower())[0].strip()
            # remove footnotes and non-alphanumeric characters
            text = re.sub(r"(\[fn.?\])", "", text)
            text = re.sub(r"[^A-Za-z ]", "", text).strip()
            # if we ended up getting some text, add it, else ignore it
            if text:
                inner_dates.append((clean_string(text), d))
            else:
                inner_dates.append((None, d))
        dates.append(inner_dates)

    return dates


def get_court_id(raw_court: str) -> Optional[str]:
    """Get court id using courts-db
    :param raw_court: Court text
    return: court id or None
    """
    for bankruptcy in [False, True]:
        # Remove dot at end, try to get a partial string match, try with and
        # without bankruptcy flag
        found_court = find_court(
            raw_court.strip("."),
            bankruptcy=bankruptcy,
            location=None,
            allow_partial_matches=True,
        )
        if found_court:
            return found_court[0]

    return None


def get_text(xml_filepath: str) -> dict:
    """Convert xml data into dict
    :param xml_filepath: path of xml file
    :return: dict with data
    """

    with open(xml_filepath, "r") as f:
        content = f.read()

    data = {}
    opinions = []

    soup = BeautifulSoup(content, "lxml")
    data["unpublished"] = False

    # Prepare opinions
    opinion = soup.find("opinion")
    if opinion:
        # Outer tag is <opinion>
        data["unpublished"] = bool(opinion.get("unpublished"))

    find_opinions = soup.findAll(re.compile("[A-Za-z]+_text"))
    order = 0
    for op in find_opinions:
        opinion_author = ""
        byline = op.find_previous_sibling()

        if byline:
            opinion_author = byline.get_text()

        opinion_type = op.name.replace("_text", "")

        new_opinion = {
            "byline": opinion_author,
            "type": opinion_type,
            "raw_opinion": op,
            "opinion": op.decode_contents(),
            "order": order,
        }

        opinions.append(new_opinion)
        order = order + 1

    SIMPLE_TAGS = [
        "attorneys",
        "caption",
        "citation",
        "court",
        "date",
        "docket",
        "hearing_date",
        "panel",
        "posture",
        "reporter_caption",
        "syllabus",
    ]

    for tag in SIMPLE_TAGS:
        found_tags = soup.findAll(tag)
        for found_tag in found_tags:
            # remove inner <citation> and <page-number> tags and content
            extra_tags_to_remove = found_tag.findAll(
                re.compile("citation|page-number")
            )
            if extra_tags_to_remove:
                for r in extra_tags_to_remove:
                    if r.next_sibling:
                        if type(r.next_sibling) == NavigableString:
                            # raw string
                            r.next_sibling.extract()
                        else:
                            print(">>> Not navigable string", r.next_sibling)
                    r.extract()

        # We use space as a separator to add a space when we have one tag
        # next to other without a space, ee try to remove double spaces
        data[tag] = [
            re.sub(" +", " ", found_tag.get_text(separator=" ").strip())
            for found_tag in found_tags
        ]

    # Add opinions to dict
    data["opinions"] = opinions

    return data


def parse_file(file_path: str) -> dict:
    """Parses a file, turning it into a correctly formatted dictionary,
    ready to be used by a populate script.
    :param file_path: A path the file to be parsed.
    :return: dict with parsed data
    """

    raw_info = get_text(file_path)
    info = {
        "unpublished": raw_info["unpublished"],
        "file": os.path.splitext(os.path.basename(file_path))[0],
        "docket": "".join(raw_info.get("docket", [])) or None,
        "citations": raw_info.get("citation", []),
        "attorneys": "".join(raw_info.get("attorneys", [])) or None,
        "posture": "".join(raw_info.get("posture", [])) or None,
        "court_id": get_court_id(" ".join(raw_info.get("court", []))),
    }
    # get basic info
    if not info["court_id"]:
        raise Exception(
            f"Failed to find a court ID for \"{''.join(raw_info.get('court', []))}\"."
        )

    # get the full panel text and extract judges from it
    panel_text = "".join(raw_info.get("panel", []))

    info["panel"] = extract_judge_last_name(panel_text) or []

    # get case names
    info["case_name_full"] = (
        format_case_name("".join(raw_info.get("caption", []))) or ""
    )
    case_name = (
        format_case_name("".join(raw_info.get("reporter_caption", []))) or ""
    )

    if case_name:
        info["case_name"] = case_name
    else:
        if info["case_name_full"]:
            # Sometimes the <caption> node has values and the <reporter_caption>
            # node does not. Fall back to <caption> in this case.
            info["case_name"] = info["case_name_full"]
    if not info["case_name"]:
        raise Exception(
            "Failed to find case_name, even after falling back to "
            "case_name_full value."
        )
    info["case_name_short"] = (
        CASE_NAME_TWEAKER.make_case_name_short(info["case_name"]) or ""
    )

    # get dates
    dates = raw_info.get("date", []) + raw_info.get("hearing_date", [])
    info["dates"] = parse_dates(dates)

    info["opinions"] = []
    judges = []
    first_chunk = 1000

    for opinion in raw_info.get("opinions", []):
        per_curiam = False
        opinion_author = ""
        if opinion.get("byline"):
            if "per curiam" in opinion["byline"][:first_chunk].lower():
                per_curiam = True
            else:
                opinion_author = extract_judge_last_name(opinion.get("byline"))

                if opinion_author:
                    judges.append(titlecase(opinion_author[0]))

        info["opinions"].append(
            {
                "opinion": opinion.get("opinion"),
                # "opinion_texts": last_texts,
                "type": opinion.get("type"),
                "author": titlecase(opinion_author[0])
                if opinion_author
                else None,
                "joining": judges[1:] if len(judges) > 1 else [],
                "byline": opinion_author,
                "per_curiam": per_curiam,
            }
        )

        if judges:
            info["judges"] = ", ".join(judges)
        else:
            info["judges"] = ""

    # Add the same sha1 and path values to every opinion (multiple opinions
    # can come from a single XML file).
    sha1 = sha1_of_file(file_path)
    for opinion in info["opinions"]:
        opinion["sha1"] = sha1
        opinion["local_path"] = file_path

    return info


def parse_opinions(options):
    """Runs through a directory of the form /data/[state]/[sub]/.../[folders]/[.xml documents].
    Parses each .xml document, instantiates the associated model object, and
    saves the object. Prints/logs status updates and tracebacks instead of
    raising exceptions.
    """

    dir_path = options["dir"][0]
    limit = options["limit"]
    random_order = options["random"]
    status_interval = options["status"]
    new_cases = options["new_cases"]
    skip_dupes = options["skip_dupes"]
    skip_new_cases = options["skip_new_cases"]
    avoid_no_cites = options["avoid_no_cites"]
    court_dates = options["court_dates"]
    start_folder = options["start_folder"]
    start_file = options["start_file"]
    debug = options["debug"]

    if limit:
        total = limit
    elif not random_order:
        logger.info("Getting an initial file count...")
        total = 0
        for _, _, file_names in os.walk(dir_path):
            total += len(fnmatch.filter(file_names, "*.xml"))
    else:
        total = None

    # go through the files, yielding parsed files and printing status
    # updates as we go
    folders = glob(f"{dir_path}/*")
    folders.sort()
    count = 0

    # get the earliest dates for each court
    if new_cases:
        logger.info("Only new cases: getting earliest dates by court.")
        min_dates = get_min_dates()
    else:
        min_dates = None

    if avoid_no_cites:
        if new_cases:
            raise Exception(
                "Cannot use both avoid_no_cites and new_cases options."
            )
        logger.info(
            "Avoiding no cites: getting earliest dates by court with "
            "no citation."
        )
        min_dates = get_min_nocite()

    if court_dates:
        start_dates = get_courtdates()
    else:
        start_dates = None

    # check if skipping first columbia's cases
    if skip_new_cases:
        skip_list = get_path_list()
    else:
        skip_list = set()

    # start/resume functionality
    if start_folder is not None:
        skip_folder = True
    else:
        skip_folder = False
    if start_file is not None:
        skip_file = True
    else:
        skip_file = False

    for folder in folders:
        if skip_folder:
            if start_folder is not None:
                check_folder = folder.split("/")[-1]
                if check_folder == start_folder:
                    skip_folder = False
                else:
                    continue
        logger.debug(folder)

        for path in file_generator(folder, random_order, limit):
            if skip_file:
                if start_file is not None:
                    check_file = path.split("/")[-1]
                    if check_file == start_file:
                        skip_file = False
                    else:
                        continue

            if path in skip_list:
                continue

            # try to parse/save the case and show any exceptions with full
            # tracebacks
            try:
                logger.info(f"Processing opinion at {path}")
                parsed = parse_file(path)
                add_new_case(parsed, skip_dupes, min_dates, start_dates, debug)
            except Exception as e:
                # show simple exception summaries for known problems
                known = [
                    "mismatched tag",
                    "Failed to get a citation",
                    "Failed to find a court ID",
                    'null value in column "date_filed"',
                    "duplicate(s)",
                ]
                if any(k in str(e) for k in known):
                    logger.info(f"Known exception in file '{path}': {str(e)}")
                else:
                    logger.info(f"Unknown exception in file '{path}':")
                    logger.info(traceback.format_exc())
        # status update
        count += 1
        if count % status_interval == 0:
            if total:
                logger.info(f"Finished {count} out of {total} files.")
            else:
                logger.info(f"Finished {count} files.")


def file_generator(dir_path: str, random_order: bool = False, limit=None):
    """Generates full file paths to all xml files in `dir_path`.

    :param dir_path: The path to get files from.
    :param random_order: If True, will generate file names randomly (possibly
     with repeats) and will never stop generating file names.
    :param limit: If not None, will limit the number of files generated to this
     integer.
    """
    count = 0
    if not random_order:
        for root, dir_names, file_names in os.walk(dir_path):
            file_names.sort()
            for file_name in fnmatch.filter(file_names, "*.xml"):
                yield os.path.join(root, file_name).replace("\\", "/")
                count += 1
                if count == limit:
                    return
    else:
        for root, dir_names, file_names in os.walk(dir_path):
            shuffle(dir_names)
            names = fnmatch.filter(file_names, "*.xml")
            if names:
                shuffle(names)
                yield os.path.join(root, names[0]).replace("\\", "/")
                break
        count += 1
        if count == limit:
            return


class Command(VerboseCommand):
    help = (
        "Parses the xml files in the specified directory into opinion "
        "objects that are saved."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "dir",
            nargs="+",
            type=str,
            help="The directory that will be recursively searched for xml "
            "files.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit on how many files to run through. By default will run "
            "through all (or if `--random`, forever).",
        )
        parser.add_argument(
            "--random",
            action="store_true",
            default=False,
            help="If set, will run through the directories and files in "
            "random order.",
        )
        parser.add_argument(
            "--status",
            type=int,
            default=100,
            help="How often a status update will be given. By default, every "
            "100 files.",
        )
        parser.add_argument(
            "--new_cases",
            action="store_true",
            default=False,
            help="If set, will skip court-years that already have data.",
        )
        parser.add_argument(
            "--skip_dupes",
            action="store_true",
            default=False,
            help="If set, will skip duplicates.",
        )
        parser.add_argument(
            "--skip_new_cases",
            action="store_true",
            default=False,
            help="If set, will skip cases from initial columbia import.",
        )
        parser.add_argument(
            "--avoid_no_cites",
            action="store_true",
            default=False,
            help="If set, will not import dates after the earliest case without a citation.",
        )
        parser.add_argument(
            "--court_dates",
            action="store_true",
            default=False,
            help="If set, will throw exception for cases before court was founded.",
        )
        parser.add_argument(
            "--start_folder",
            type=str,
            default=None,
            help="The folder (state name) to start on.",
        )
        parser.add_argument(
            "--start_file",
            type=str,
            default=None,
            help="The file name to start on (if resuming).",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Don't change the data.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        parse_opinions(options)
