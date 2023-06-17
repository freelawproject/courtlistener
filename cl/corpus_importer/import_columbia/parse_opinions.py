"""
Functions to parse court data in XML format into a list of dictionaries.
"""
import os
import re

import dateutil.parser as dparser
from bs4 import BeautifulSoup, NavigableString
from juriscraper.lib.string_utils import (
    CaseNameTweaker,
    clean_string,
    harmonize,
    titlecase,
)

from cl.corpus_importer.court_regexes import state_pairs
from cl.lib.crypto import sha1_of_file
from cl.people_db.lookup_utils import extract_judge_last_name

from .regexes_columbia import FOLDER_DICT, SPECIAL_REGEXES

# initialized once since it takes resources
CASE_NAME_TWEAKER = CaseNameTweaker()

# tags for which content will be condensed into plain text
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

# regex that will be applied when condensing SIMPLE_TAGS content
STRIP_REGEX = [r"</?citation.*>", r"</?page_number.*>"]

# types of opinions that will be parsed
# each may have a '_byline' and '_text' node
OPINION_TYPES = ["opinion", "dissent", "concurrence"]


def parse_file(file_path):
    """Parses a file, turning it into a correctly formatted dictionary, ready to
    be used by a populate script.

    :param file_path: A path the file to be parsed.
    object. The regexes associated to its value in special_regexes will be used.
    """
    raw_info = get_text(file_path)
    info = {}
    # get basic info
    info["unpublished"] = raw_info["unpublished"]
    info["file"] = os.path.splitext(os.path.basename(file_path))[0]
    info["docket"] = "".join(raw_info.get("docket", [])) or None
    info["citations"] = raw_info.get("citation", [])
    info["attorneys"] = "".join(raw_info.get("attorneys", [])) or None
    info["posture"] = "".join(raw_info.get("posture", [])) or None
    info["court_id"] = (
        get_state_court_object("".join(raw_info.get("court", [])), file_path)
        or None
    )
    if not info["court_id"]:
        raise Exception(
            f"Failed to find a court ID for \"{''.join(raw_info.get('court', []))}\"."
        )

    # get the full panel text and extract judges from it
    panel_text = "".join(raw_info.get("panel", []))
    # if panel_text:
    #    judge_info.append(('Panel\n-----', panel_text))
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

    # figure out if this case was heard per curiam by checking the first chunk
    # of text in fields in which this is usually indicated
    info["per_curiam"] = False
    first_chunk = 1000
    for opinion in raw_info.get("opinions", []):
        if "per curiam" in opinion["opinion"][:first_chunk].lower():
            info["per_curiam"] = True
            break
        if (
            opinion["byline"]
            and "per curiam" in opinion["byline"][:first_chunk].lower()
        ):
            info["per_curiam"] = True
            break

    # condense opinion texts if there isn't an associated byline
    # print a warning whenever we're appending multiple texts together
    info["opinions"] = []
    judges = []

    for opinion in raw_info.get("opinions", []):
        opinion_author = ""
        if opinion.get("byline"):
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
                # "joining": judges[1:] if len(judges) > 0 else [],
                "byline": opinion_author,
            }
        )

        if judges:
            info["judges"] = ", ".join(judges)
        else:
            info["judges"] = ""

    # check if opinions were heard per curiam by checking if the first chunk of
    # text in the byline or in any of its associated opinion texts indicate this
    for opinion in info["opinions"]:
        # if there's already an identified author, it's not per curiam
        if opinion["author"]:
            opinion["per_curiam"] = False
            continue
        # otherwise, search through chunks of text for the phrase 'per curiam'
        per_curiam = False
        first_chunk = 1000
        if "per curiam" in opinion["byline"][:first_chunk].lower():
            per_curiam = True
        opinion["per_curiam"] = per_curiam

    # construct the plain text info['judges'] from collected judge data
    # info['judges'] = '\n\n'.join('%s\n%s' % i for i in judge_info)

    # Add the same sha1 and path values to every opinion (multiple opinions
    # can come from a single XML file).
    sha1 = sha1_of_file(file_path)
    for opinion in info["opinions"]:
        opinion["sha1"] = sha1
        opinion["local_path"] = file_path

    return info


def get_text(xml_filepath: str):
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
                            print(">>> not navigable string", r.next_sibling)
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


def parse_dates(raw_dates):
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


def format_case_name(n):
    """Applies standard harmonization methods after normalizing with
    lowercase."""
    return titlecase(harmonize(n.lower()))


def get_state_court_object(raw_court, file_path):
    """Get the court object from a string. Searches through `state_pairs`.

    :param raw_court: A raw court string, parsed from an XML file.
    :param file_path: xml filepath
    this key in `SPECIAL_REGEXES`.
    """
    if "[" in raw_court and "]" in raw_court:
        i = raw_court.find("[")
        j = raw_court.find("]") + 1

        raw_court = (raw_court[:i] + raw_court[j:]).strip()

    raw_court = raw_court.strip(".")

    for regex, value in state_pairs:
        if re.search(regex, raw_court):
            return value

    # this messes up for, e.g. 'St. Louis', and 'U.S. Circuit Court, but works
    # for all others
    if "." in raw_court and not any([s in raw_court for s in ["St.", "U.S"]]):
        j = raw_court.find(".")
        r = raw_court[:j]

        for regex, value in state_pairs:
            if re.search(regex, r):
                return value

    # we need the comma to successfully match Superior Courts, the name of which
    # comes after the comma
    if "," in raw_court and "Superior Court" not in raw_court:
        j = raw_court.find(",")
        r = raw_court[:j]

        for regex, value in state_pairs:
            if re.search(regex, r):
                return value
    # Reduce to: /data/.../alabama/court_opinions'
    root_folder = file_path.split("/documents")[0]
    # Get the last two dirs off the end, leaving: 'alabama/court_opinions'
    folder = "/".join(root_folder.split("/")[-2:])
    if folder in SPECIAL_REGEXES:
        for regex, value in SPECIAL_REGEXES[folder]:
            if re.search(regex, raw_court):
                return value
    if folder in FOLDER_DICT:
        return FOLDER_DICT[folder]
