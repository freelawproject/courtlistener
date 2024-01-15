# Functions to parse court data in XML format into a list of dictionaries.
import os
import re
import xml.etree.cElementTree as ET

import dateutil.parser as dparser
from juriscraper.lib.string_utils import (
    CaseNameTweaker,
    clean_string,
    harmonize,
    titlecase,
)
from lxml import etree

from cl.corpus_importer.court_regexes import state_pairs
from cl.lib.crypto import sha1_of_file
from cl.people_db.lookup_utils import extract_judge_last_name

from .regexes_columbia import FOLDER_DICT, SPECIAL_REGEXES

# initialized once since it takes resources
CASE_NAME_TWEAKER = CaseNameTweaker()

# tags for which content will be condensed into plain text
SIMPLE_TAGS = [
    "reporter_caption",
    "citation",
    "caption",
    "court",
    "docket",
    "posture",
    "date",
    "hearing_date",
    "panel",
    "attorneys",
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
    :param court_fallback: A string used as a fallback in getting the court
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
    for current_type in OPINION_TYPES:
        last_texts = []
        for opinion in raw_info.get("opinions", []):
            if opinion["type"] != current_type:
                continue
            last_texts.append(opinion["opinion"])
            if opinion["byline"]:
                # judge_info.append((
                #    '%s Byline\n%s' % (current_type.title(), '-' * (len(current_type) + 7)),
                #    opinion['byline']
                # ))
                # add the opinion and all of the previous texts
                judges = extract_judge_last_name(opinion["byline"])
                info["opinions"].append(
                    {
                        "opinion": "\n".join(last_texts),
                        "opinion_texts": last_texts,
                        "type": current_type,
                        "author": judges[0] if judges else None,
                        "joining": judges[1:] if len(judges) > 0 else [],
                        "byline": opinion["byline"],
                    }
                )
                last_texts = []
                if current_type == "opinion":
                    info["judges"] = opinion["byline"]

        if last_texts:
            relevant_opinions = [
                o for o in info["opinions"] if o["type"] == current_type
            ]
            if relevant_opinions:
                relevant_opinions[-1]["opinion"] += "\n%s" % "\n".join(
                    last_texts
                )
                relevant_opinions[-1]["opinion_texts"].extend(last_texts)
            else:
                info["opinions"].append(
                    {
                        "opinion": "\n".join(last_texts),
                        "opinion_texts": last_texts,
                        "type": current_type,
                        "author": None,
                        "joining": [],
                        "byline": "",
                    }
                )

    # check if opinions were heard per curiam by checking if the first chunk of
    # text in the byline or in any of its associated opinion texts indicate this
    for opinion in info["opinions"]:
        # if there's already an identified author, it's not per curiam
        if opinion["author"] > 0:
            opinion["per_curiam"] = False
            continue
        # otherwise, search through chunks of text for the phrase 'per curiam'
        per_curiam = False
        first_chunk = 1000
        if "per curiam" in opinion["byline"][:first_chunk].lower():
            per_curiam = True
        else:
            for text in opinion["opinion_texts"]:
                if "per curiam" in text[:first_chunk].lower():
                    per_curiam = True
                    break
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


def get_text(file_path):
    """Reads a file and returns a dictionary of grabbed text.

    :param file_path: A path the file to be parsed.
    """
    with open(file_path, "r") as f:
        file_string = f.read()
    raw_info = {}

    # used when associating a byline of an opinion with the opinion's text
    current_byline = {"type": None, "name": None}

    # if this is an unpublished opinion, note this down and remove all
    # <unpublished> tags
    raw_info["unpublished"] = False
    if "<opinion unpublished=true>" in file_string:
        file_string = file_string.replace(
            "<opinion unpublished=true>", "<opinion>"
        )
        file_string = file_string.replace("<unpublished>", "").replace(
            "</unpublished>", ""
        )
        raw_info["unpublished"] = True

    # turn the file into a readable tree
    attempts = [
        {"recover": False, "replace": False},
        {"recover": False, "replace": True},
        {"recover": True, "replace": False},
        {"recover": True, "replace": True},
    ]
    replaced_string = file_string.replace(
        "</footnote_body></block_quote>", "</block_quote></footnote_body>"
    )
    for attempt in attempts:
        try:
            s = replaced_string if attempt["replace"] else file_string
            if attempt["recover"]:
                # This recovery mechanism is sometimes crude, but it can be very
                # effective in re-arranging mismatched tags.
                parser = etree.XMLParser(recover=True)
                root = etree.fromstring(s, parser=parser)
            else:
                # Normal case
                root = etree.fromstring(s)
            break
        except etree.ParseError as e:
            if attempt == attempts[-1]:
                # Last attempt. Re-raise the exception.
                raise e

    for child in root.iter():
        # if this child is one of the ones identified by SIMPLE_TAGS, just grab
        # its text
        if child.tag in SIMPLE_TAGS:
            # strip unwanted tags and xml formatting
            text = get_xml_string(child)
            for r in STRIP_REGEX:
                text = re.sub(r, "", text)
            text = re.sub(r"<.*?>", " ", text).strip()
            # put into a list associated with its tag
            raw_info.setdefault(child.tag, []).append(text)
            continue

        # Set aside any text in the root of the file. Sometimes this is the only
        # text we get.
        if child.tag == "opinion":
            direct_descendant_text = " ".join(child.xpath("./text()"))

        for opinion_type in OPINION_TYPES:
            # if this child is a byline, note it down and use it later
            if child.tag == f"{opinion_type}_byline":
                current_byline["type"] = opinion_type
                current_byline["name"] = get_xml_string(child)
                break
            # if this child is an opinion text blob, add it to an incomplete
            # opinion and move into the info dict
            if child.tag == f"{opinion_type}_text":
                # add the full opinion info, possibly associating it to a byline
                raw_info.setdefault("opinions", []).append(
                    {
                        "type": opinion_type,
                        "byline": current_byline["name"]
                        if current_byline["type"] == opinion_type
                        else None,
                        "opinion": get_xml_string(child),
                    }
                )
                current_byline["type"] = current_byline["name"] = None
                break

    # Some opinions do not have an opinion node. Create an empty node here. This
    # will at least ensure that an opinion object is created.
    if raw_info.get("opinions") is None:
        raw_info["opinions"] = [
            {
                "type": "opinion",
                "byline": None,
                "opinion": direct_descendant_text or "",
            }
        ]
    return raw_info


def get_xml_string(e):
    """Returns a normalized string of the text in <element>.

    :param e: An XML element.
    """
    inner_string = re.sub(
        r"(^<%s\b.*?>|</%s\b.*?>$)" % (e.tag, e.tag), "", ET.tostring(e)
    )
    return inner_string.decode().strip()


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
    :param fallback: If fail to find one, will apply the regexes associated to
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
    if "." in raw_court and not any(s in raw_court for s in ["St.", "U.S"]):
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


if __name__ == "__main__":
    parsed = parse_file(
        "/vagrant/flp/columbia_data/opinions/01910ad13eb152b3.xml"
    )
    pass
