"""
Command to import opinions from columbia xlml file

Import using a csv file with xml file path pointing to mounted directory and file path
docker-compose -f docker/courtlistener/docker-compose.yml exec cl-django python manage.py import_columbia --csv /opt/courtlistener/cl/assets/media/testfile.csv

Csv example:
filepath
/opt/columbia/michigan/supreme_court_opinions/documents/d5a484f1bad20ba0.xml

Import specifying the mounted directory where the xml files are located
docker-compose -f docker/courtlistener/docker-compose.yml exec cl-django python manage.py import_columbia  --dir /opt/courtlistener/cl/assets/media/columbia/alabama/
"""
import csv
import fnmatch
import os
import re
import traceback
from datetime import date
from glob import glob
from random import shuffle
from typing import Any, Optional

import dateutil.parser as dparser
from bs4 import BeautifulSoup, NavigableString, Tag
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
) -> list[list[tuple[Any, date] | tuple[None, date]]]:
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


def get_court_id(raw_court: str) -> list[str]:
    """Get court id using courts-db
    :param raw_court: Court text
    return: court id or None
    """

    # Replace double spaces,
    court_text = re.sub(" +", " ", raw_court)
    # Replace \n and remove dot at end
    court_text = court_text.replace("\n", "").strip(".")

    for bankruptcy in [False, True]:
        # Remove dot at end, try to get a partial string match, try with and
        # without bankruptcy flag
        found_court = find_court(
            court_text,
            bankruptcy=bankruptcy,
            location=None,
            allow_partial_matches=True,
        )
        if found_court:
            return found_court

    return []


def get_text(xml_filepath: str) -> dict:
    """Convert xml data into dict
    :param xml_filepath: path of xml file
    :return: dict with data
    """

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
    ]

    data = {}  # type: dict

    with open(xml_filepath, "r", encoding="utf-8") as f:
        file_content = f.read()

        data["unpublished"] = False

        if "<opinion unpublished=true>" in file_content:
            file_content = file_content.replace(
                "<opinion unpublished=true>", "<opinion>"
            )
            file_content = file_content.replace("<unpublished>", "").replace(
                "</unpublished>", ""
            )

            data["unpublished"] = True

    # Sometimes opening and ending tag mismatch (e.g. c6b39dcb29c9c.xml)
    file_content = file_content.replace(
        "</footnote_body></block_quote>", "</block_quote></footnote_body>"
    )

    soup = BeautifulSoup(file_content, "lxml")

    # Find the outer <opinion> tag to have all elements inside
    find_opinion = soup.find("opinion")

    step_one_opinions = []  # type: list
    opinions = []  # type: list
    order = 0

    if find_opinion:
        untagged_content = []

        # We iterate all content, with and without tags
        # STEP 1: Extract all content in multiple dict elements
        for i, content in enumerate(find_opinion):  # type: int, Tag
            if type(content) == NavigableString:
                # We found a raw string, store it
                untagged_content.append(str(content))

            else:
                if content.name in SIMPLE_TAGS + [
                    "citation_line",
                    "opinion_byline",
                    "dissent_byline",
                    "concurrence_byline",
                ]:
                    # Ignore these tags, it will be processed later
                    continue
                elif content.name in [
                    "opinion_text",
                    "dissent_text",
                    "concurrence_text",
                ]:
                    if untagged_content:
                        # We found something other than a navigable string that is
                        # not an opinion, but now we have found an opinion,
                        # let's create this content first

                        # default type
                        op_type = "opinion"
                        if step_one_opinions:
                            if step_one_opinions[-1].get("type"):
                                # use type of previous opinion if exists
                                op_type = step_one_opinions[-1].get("type")

                        # Get rid of double spaces
                        opinion_content = re.sub(
                            " +", " ", "\n".join(untagged_content)
                        ).strip()  # type: str
                        if opinion_content:
                            step_one_opinions.append(
                                {
                                    "opinion": opinion_content,
                                    "order": order,
                                    "byline": "",
                                    "type": op_type,
                                }
                            )
                            order = order + 1
                        untagged_content = []

                    byline = content.find_previous_sibling()
                    opinion_author = ""
                    if byline and "_byline" in byline.name:
                        opinion_author = byline.get_text()

                    opinion_content = re.sub(
                        " +", " ", content.decode_contents()
                    ).strip()
                    if opinion_content:
                        step_one_opinions.append(
                            {
                                "opinion": opinion_content,
                                "order": order,
                                "byline": opinion_author,
                                "type": content.name.replace("_text", ""),
                            }
                        )
                        order = order + 1

                else:
                    if content.name not in SIMPLE_TAGS + ["syllabus"]:
                        # We store content that is not inside _text tag and is not in
                        # one of the known non-opinion tags
                        untagged_content.append(str(content))

        if untagged_content:
            # default type
            op_type = "opinion"
            if step_one_opinions:
                if step_one_opinions[-1].get("type"):
                    # use type of previous opinion if exists
                    op_type = step_one_opinions[-1].get("type")

            opinion_content = re.sub(
                " +", " ", "\n".join(untagged_content)
            ).strip()
            if opinion_content:
                step_one_opinions.append(
                    {
                        "opinion": opinion_content,
                        "order": order,
                        "byline": "",
                        "type": op_type,
                    }
                )

        # Step 2: Merge found content in the xml file
        new_order = 0
        authorless_content = []

        for i, found_content in enumerate(step_one_opinions, start=1):
            byline = found_content.get("byline")
            if not byline:
                # Opinion has no byline, store it
                authorless_content.append(found_content)

            if byline:
                # Opinion has byline
                opinion_type = found_content.get("type")
                opinion_content = found_content.get("opinion", "")
                # Store content that doesn't match the current type
                alternative_authorless_content = [
                    z
                    for z in authorless_content
                    if z.get("type") != opinion_type
                ]
                # Keep content that matches the current type
                authorless_content = [
                    z
                    for z in authorless_content
                    if z.get("type") == opinion_type
                ]

                if alternative_authorless_content:
                    # Keep floating text that are not from the same type,
                    # we need to create a separate opinion for those,
                    # for example: in 2713f39c5a8e8684.xml we have an opinion
                    # without an author, and the next opinion with an author is
                    # a dissent opinion, we can't combine both

                    # We check if the previous stored opinion matches the type of the
                    # content
                    relevant_opinions = (
                        [opinions[-1]]
                        if opinions
                        and opinions[-1]["type"]
                        == alternative_authorless_content[0].get("type")
                        else []
                    )

                    if relevant_opinions:
                        previous_opinion = relevant_opinions[-1]
                        if previous_opinion.get(
                            "type"
                        ) == alternative_authorless_content[0].get("type"):
                            # Merge last opinion with previous opinion, it probably
                            # belongs the same author
                            relevant_opinions[-1][
                                "opinion"
                            ] += "\n" + "\n".join(
                                [
                                    f.get("opinion")
                                    for f in alternative_authorless_content
                                    if f.get("opinion")
                                ]
                            )
                        authorless_content = []

                    else:
                        # No relevant opinions found, create a new opinion
                        new_opinion = {
                            "byline": None,
                            "type": alternative_authorless_content[0].get(
                                "type"
                            ),
                            "opinion": "\n".join(
                                [
                                    f.get("opinion")
                                    for f in alternative_authorless_content
                                    if f.get("opinion")
                                ]
                            ),
                            "order": new_order,
                        }
                        new_order = new_order + 1
                        opinions.append(new_opinion)

                # Add new opinion
                new_opinion = {
                    "byline": byline,
                    "type": opinion_type,
                    "opinion": "\n".join(
                        [
                            f.get("opinion")
                            for f in authorless_content
                            if f.get("type") == opinion_type
                        ]
                    )
                    + "\n\n"
                    + opinion_content,
                    "order": new_order,
                }

                opinions.append(new_opinion)
                new_order = new_order + 1
                authorless_content = []

            if len(step_one_opinions) == i and authorless_content:
                # If is the last opinion, and we still have opinions without
                # byline, create an opinion without an author and the contents
                # that couldn't be merged

                # We check if the previous stored opinion matches the type of the
                # content
                relevant_opinions = (
                    [opinions[-1]]
                    if opinions
                    and opinions[-1]["type"]
                    == authorless_content[0].get("type")
                    else []
                )

                if relevant_opinions:
                    previous_opinion = relevant_opinions[-1]
                    if previous_opinion.get("type") == authorless_content[
                        0
                    ].get("type"):
                        # Merge last opinion with previous opinion, it probably
                        # belongs the same author
                        relevant_opinions[-1]["opinion"] += "\n" + "\n".join(
                            [
                                f.get("opinion")
                                for f in authorless_content
                                if f.get("opinion")
                            ]
                        )

                else:
                    # Create last floating opinion
                    new_opinion = {
                        "byline": None,
                        "type": authorless_content[0].get("type"),
                        "opinion": "\n".join(
                            [
                                f.get("opinion")
                                for f in authorless_content
                                if f.get("opinion")
                            ]
                        ),
                        "order": new_order,
                    }
                    opinions.append(new_opinion)

    for tag in SIMPLE_TAGS:
        found_tags = soup.findAll(tag)
        for found_tag in found_tags:
            # remove inner <citation> and <page_number> tags and content
            extra_tags_to_remove = found_tag.findAll(
                re.compile("citation|page_number")
            )
            if extra_tags_to_remove:
                for r in extra_tags_to_remove:
                    if tag == "reporter_caption":
                        # The reporter_caption may contain the location, and we need
                        # to remove it to make the name cleaner, e.g. Tex.App.-Ft.
                        # Worth [2d Dist.] 2002
                        if r.next_sibling:
                            if type(r.next_sibling) == NavigableString:
                                # The element is not tagged, it is just a text
                                # string
                                r.next_sibling.extract()
                    r.extract()

        # We use space as a separator to add a space when we have one tag next to
        # other without a space
        data[tag] = [
            found_tag.get_text(separator=" ").strip()
            for found_tag in found_tags
        ]

        if tag in ["attorneys", "posture"]:
            # Replace multiple line breaks in this specific fields
            data[tag] = [re.sub("\n+", " ", c) for c in data.get(tag, [])]

        if tag in ["reporter_caption"]:
            # Remove the last comma from the case name
            data[tag] = [c.rstrip(",") for c in data.get(tag, [])]

        # Remove repeated spaces
        data[tag] = [re.sub(" +", " ", c) for c in data.get(tag, [])]

        if tag == "citation":
            # Sometimes we have multiple citation tags with same citation,
            # we need to remove duplicates (e.g. ebbde4042b7a019c.xml)
            data[tag] = list(set(data[tag]))

    # Get syllabus from file
    data["syllabus"] = "\n".join(
        [s.decode_contents() for s in soup.findAll("syllabus")]
    )

    # Add opinions to dict
    data["opinions"] = opinions

    return data


def fix_filepath(xml_path: str, xml_dir: str) -> str:
    """Build the correct filepath to xml file
    :param xml_path: current file path
    :param xml_dir: mounted dir where the xml files are
    :return: fixed filepath with mounted dir
    """
    if (
        xml_path
        and "/home/mlissner/columbia/opinions/" in xml_path
        or "/Users/Palin/Work/columbia/usb/" in xml_path
    ):
        filepath = xml_path.replace(
            "/home/mlissner/columbia/opinions/", ""
        ).replace("/Users/Palin/Work/columbia/usb/", "")
        return os.path.join(xml_dir, filepath)

    return os.path.join(xml_dir, xml_path)


def parse_file(
    file_path: str, xml_dir: Optional[str] = None, csv_file: bool = False
) -> dict:
    """Parses a file, turning it into a correctly formatted dictionary,
    ready to be used by a populate script.
    :param file_path: A path the file to be parsed.
    :param xml_dir: path to mounted dir
    :return: dict with parsed data
    """

    if csv_file and xml_dir:
        file_path = fix_filepath(file_path, xml_dir)

    raw_info = get_text(file_path)
    info = {
        "unpublished": raw_info["unpublished"],
        "syllabus": raw_info["syllabus"],
        "file": os.path.splitext(os.path.basename(file_path))[0],
        "docket": "".join(raw_info.get("docket", [])) or None,
        "citations": raw_info.get("citation", []),
        "attorneys": "".join(raw_info.get("attorneys", [])) or None,
        "posture": "".join(raw_info.get("posture", [])) or None,
        "courts": get_court_id(" ".join(raw_info.get("court", []))),
        "court_id": "",
    }

    # get basic info
    if not info["courts"]:
        raise Exception(
            f"Failed to find a court ID for \"{''.join(raw_info.get('court', []))}\"."
        )

    if len(info["courts"]) == 1:
        info["court_id"] = info["courts"][0]
    else:
        raise Exception(
            f"Multiple matches found for court: \"{', '.join(info['courts'])}\""
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
            # Sometimes the <caption> node has values and the
            # <reporter_caption> node does not. Fall back to <caption> in
            # this case.
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


def process_csv_file(csv_path: str, debug: bool, mounted_xml_dir: str) -> None:
    """
    Import xml files from a list of paths in csv file
    :param csv_path: Absolute path to csv file
    :param mounted_xml_dir: Path to mounted dir
    :param debug: set true to fake process
    """
    logger.info(f"Loading csv file at {csv_path}")

    with open(csv_path, mode="r", encoding="utf-8") as csv_file:
        csv_reader = csv.DictReader(csv_file)

        for row in csv_reader:
            xml_path = row.get("filepath")
            if xml_path and os.path.exists(xml_path):
                try:
                    logger.info(f"Processing opinion at {xml_path}")
                    parsed = parse_file(
                        xml_path, xml_dir=mounted_xml_dir, csv_file=True
                    )
                    add_new_case(parsed, testing=debug)
                except Exception as e:
                    known = [
                        "mismatched tag",
                        "Failed to get a citation",
                        "Failed to find a court ID",
                        'null value in column "date_filed"',
                        "Multiple matches found for court",
                        "Found duplicate(s)",
                        "Court doesn't exist in CourtListener",
                    ]
                    if any(k in str(e) for k in known):
                        logger.info(
                            f"Known exception in file '{xml_path}': {str(e)}"
                        )
                    else:
                        logger.info(f"Unknown exception in file '{xml_path}':")
                        logger.info(traceback.format_exc())
            else:
                logger.info(f"The file doesn't exist: {xml_path}")


def parse_opinions(options) -> None:
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
                add_new_case(parsed, min_dates, start_dates, debug)
            except Exception as e:
                # show simple exception summaries for known problems
                known = [
                    "mismatched tag",
                    "Failed to get a citation",
                    "Failed to find a court ID",
                    'null value in column "date_filed"',
                    "Multiple matches found for court",
                    "Found duplicate(s)",
                    "Court doesn't exist in CourtListener",
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
                for file_name in names:
                    yield os.path.join(root, file_name).replace("\\", "/")
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
            "--dir",
            nargs="+",
            type=str,
            help="The directory that will be recursively searched for xml "
            "files.",
            required=False,
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
            "--skip_new_cases",
            action="store_true",
            default=False,
            help="If set, will skip cases from initial columbia import.",
        )
        parser.add_argument(
            "--avoid_no_cites",
            action="store_true",
            default=False,
            help="If set, will not import dates after the earliest case "
            "without a citation.",
        )
        parser.add_argument(
            "--court_dates",
            action="store_true",
            default=False,
            help="If set, will throw exception for cases before court was "
            "founded.",
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
            help="The file name with extension to start on (if resuming).",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Don't change the data.",
        )
        parser.add_argument(
            "--csv-file",
            required=False,
            help="The absolute path to the CSV containing the path to the xml files "
            "to import",
        )
        parser.add_argument(
            "--xml-dir",
            default="/tmp/columbia",
            required=False,
            help="The absolute path to the directory with columbia xml files",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        if not options["csv_file"] and not options["dir"]:
            logger.warning("At least one option required: --csv-file or --dir")
            return
        if options["csv_file"]:
            if not os.path.exists(options["csv_file"]):
                logger.warning("CSV file doesn't exist.")
                return
            process_csv_file(
                options["csv_file"], options["debug"], options["xml_dir"]
            )
        else:
            parse_opinions(options)
