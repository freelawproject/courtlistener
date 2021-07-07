import fnmatch
import os
import re
import xml.etree.cElementTree as ET
from glob import glob
from random import shuffle

import dateutil.parser as dparser

from cl.corpus_importer.court_regexes import state_pairs
from cl.corpus_importer.import_columbia.regexes_columbia import (
    FOLDER_DICT,
    SPECIAL_REGEXES,
)


def file_generator(dir_path, random_order=False, limit=None):
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


def clean_string(s):
    """Clean up strings.

    Accomplishes the following:
     - replaces HTML encoded characters with ASCII versions.
     - removes -, ' ', #, *, ; and ',' from the end of lines
     - converts to unicode.
     - removes weird white space and replaces with spaces.
    """
    # if not already unicode, make it unicode, dropping invalid characters
    # if not isinstance(s, unicode):
    # s = force_unicode(s, errors='ignore')

    # Get rid of HTML encoded chars
    s = (
        s.replace("&rsquo;", "'")
        .replace("&rdquo;", '"')
        .replace("&ldquo;", '"')
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("%20", " ")
        .replace("&#160;", " ")
    )

    # smart quotes
    s = (
        s.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
    )

    # Get rid of weird punctuation
    s = s.replace("*", "").replace("#", "").replace(";", "")

    # Strip bad stuff from the end of lines. Python's strip fails here because
    # we don't know the order of the various punctuation items to be stripped.
    # We split on the v., and handle fixes at either end of plaintiff or
    # appellant.
    bad_punctuation = r"(-|–|_|/|;|,|\s)*"
    bad_endings = re.compile(r"%s$" % bad_punctuation)
    bad_beginnings = re.compile(r"^%s" % bad_punctuation)

    s = s.split(" v. ")
    cleaned_string = []
    for frag in s:
        frag = re.sub(bad_endings, "", frag)
        frag = re.sub(bad_beginnings, "", frag)
        cleaned_string.append(frag)
    s = " v. ".join(cleaned_string)

    # get rid of '\t\n\x0b\x0c\r ', and replace them with a single space.
    s = " ".join(s.split())

    return s


# For use in harmonize function
# More details: http://www.law.cornell.edu/citation/4-300.htm
US = r"USA|U\.S\.A\.|U\.S\.?|U\. S\.?|(The )?United States of America|The United States"
UNITED_STATES = re.compile(r"^(%s)(,|\.)?$" % US, re.I)
THE_STATE = re.compile(r"the state", re.I)
ET_AL = re.compile(r",?\set\.?\sal\.?", re.I)
BW = (
    r"appell(ee|ant)s?|claimants?|complainants?|defendants?|defendants?(--?|/)appell(ee|ant)s?"
    + r"|devisee|executor|executrix|pet(\.|itioner)s?|petitioners?(--?|/)appell(ee|ant)s?"
    + r"|petitioners?(--?|/)defendants?|plaintiffs?|plaintiffs?(--?|/)appell(ee|ant)s?|respond(e|a)nts?"
    + r"|respond(e|a)nts?(--?|/)appell(ee|ant)s?|cross(--?|/)respondents?|crosss?(--?|/)petitioners?"
    + r"|cross(--?|/)appell(ees|ant)s?|deceased"
)
BAD_WORDS = re.compile(r"^(%s)(,|\.)?$" % BW, re.I)
BIG = (
    "3D|AFL|AKA|A/K/A|BMG|CBS|CDC|CDT|CEO|CIO|CNMI|D/B/A|DOJ|DVA|EFF|FCC|"
    "FTC|HSBC|IBM|II|III|IV|JJ|LLC|LLP|MCI|MJL|MSPB|ND|NLRB|PTO|SD|UPS|RSS|SEC|UMG|US|USA|USC|"
    "USPS|WTO"
)
SMALL = r"a|an|and|as|at|but|by|en|for|if|in|is|of|on|or|the|to|v\.?|via|vs\.?"
NUMS = "0123456789"
PUNCT = r"""!"#$¢%&'‘()*+,\-./:;?@[\\\]_—`{|}~"""
WEIRD_CHARS = r"¼½¾§ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜßàáâãäåæçèéêëìíîïñòóôœõöøùúûüÿ"
BIG_WORDS = re.compile(r"^(%s)[%s]?$" % (BIG, PUNCT), re.I)
SMALL_WORDS = re.compile(r"^(%s)$" % SMALL, re.I)
SMALL_WORD_INLINE = re.compile(r"(^|\s)(%s)(\s|$)" % SMALL, re.I)
INLINE_PERIOD = re.compile(r"[a-z][.][a-z]", re.I)
INLINE_SLASH = re.compile(r"[a-z][/][a-z]", re.I)
INLINE_AMPERSAND = re.compile(r"([a-z][&][a-z])(.*)", re.I)
UC_ELSEWHERE = re.compile(r"[%s]*?[a-zA-Z]+[A-Z]+?" % PUNCT)
CAPFIRST = re.compile(r"^[%s]*?([A-Za-z])" % PUNCT)
SMALL_FIRST = re.compile(r"^([%s]*)(%s)\b" % (PUNCT, SMALL), re.I)
SMALL_LAST = re.compile(r"\b(%s)[%s]?$" % (SMALL, PUNCT), re.I)
SUBPHRASE = re.compile(r"([:;?!][ ])(%s)" % SMALL)
APOS_SECOND = re.compile(r"^[dol]{1}['‘]{1}[a-z]+$", re.I)
ALL_CAPS = re.compile(r"^[A-Z\s%s%s%s]+$" % (PUNCT, WEIRD_CHARS, NUMS))
UC_INITIALS = re.compile(r"^(?:[A-Z]{1}\.{1}|[A-Z]{1}\.{1}[A-Z]{1})+,?$")
MAC_MC = re.compile(r"^([Mm]a?c)(\w+.*)")


def titlecase(text, DEBUG=False):
    """Titlecases input text

    This filter changes all words to Title Caps, and attempts to be clever
    about *un*capitalizing SMALL words like a/an/the in the input.

    The list of "SMALL words" which are not capped comes from
    the New York Times Manual of Style, plus 'vs' and 'v'.

    This will fail if multiple sentences are provided as input and if the
    first word of a sentence is a SMALL_WORD.

    List of "BIG words" grows over time as entries are needed.
    """
    text_sans_small_words = re.sub(SMALL_WORD_INLINE, "", text)
    if text_sans_small_words.isupper():
        # if, after removing small words, the entire string is uppercase,
        # we lowercase it
        if DEBUG:
            print("Entire string is uppercase, thus lowercasing.")
        text = text.lower()
    elif not text_sans_small_words.isupper() and DEBUG:
        print(f"Entire string not upper case. Not lowercasing: {text}")

    lines = re.split("[\r\n]+", text)
    processed = []
    for line in lines:
        all_caps = ALL_CAPS.match(line)
        words = re.split("[\t ]", line)
        tc_line = []
        for word in words:
            if DEBUG:
                print(f"Word: {word}")
            if all_caps:
                if UC_INITIALS.match(word):
                    if DEBUG:
                        print(f"  UC_INITIALS match for: {word}")
                    tc_line.append(word)
                    continue
                else:
                    if DEBUG:
                        print(f"  Not initials. Lowercasing: {word}")
                    word = word.lower()

            if APOS_SECOND.match(word):
                # O'Reiley, L'Oreal, D'Angelo
                if DEBUG:
                    print(f"  APOS_SECOND matched. Fixing it: {word}")
                word = word[0:3].upper() + word[3:]
                tc_line.append(word)
                continue

            if INLINE_PERIOD.search(word):
                if DEBUG:
                    print(
                        "  INLINE_PERIOD matched. Uppercasing if == 1 char: "
                        + word
                    )
                parts = word.split(".")
                new_parts = []
                for part in parts:
                    if len(part) == 1:
                        # It's an initial like U.S.
                        new_parts.append(part.upper())
                    else:
                        # It's something like '.com'
                        new_parts.append(part)
                word = ".".join(new_parts)
                tc_line.append(word)
                continue

            if INLINE_SLASH.search(word):
                # This repeats INLINE_PERIOD. Could be more elegant.
                if DEBUG:
                    print(
                        "  INLINE_SLASH matched. Uppercasing if == 1 char: "
                        + word
                    )
                parts = word.split("/")
                new_parts = []
                for part in parts:
                    if len(part) == 1:
                        # It's an initial like A/M
                        new_parts.append(part.upper())
                    else:
                        # It's something like 'True/False'
                        new_parts.append(part)
                word = "/".join(new_parts)
                tc_line.append(word)
                continue

            amp_match = INLINE_AMPERSAND.match(word)
            if amp_match:
                if DEBUG:
                    print(f"  INLINE_AMPERSAND matched. Uppercasing: {word}")
                tc_line.append(
                    f"{amp_match.group(1).upper()}{amp_match.group(2)}"
                )
                continue

            if UC_ELSEWHERE.match(word):
                if DEBUG:
                    print(f"  UC_ELSEWHERE matched. Leaving unchanged: {word}")
                tc_line.append(word)
                continue

            if SMALL_WORDS.match(word):
                if DEBUG:
                    print(f"  SMALL_WORDS matched. Lowercasing: {word}")
                tc_line.append(word.lower())
                continue

            if BIG_WORDS.match(word):
                if DEBUG:
                    print(f"  BIG_WORDS matched. Uppercasing: {word}")
                tc_line.append(word.upper())
                continue

            match = MAC_MC.match(word)
            if match and (word not in ["mack", "machine"]):
                if DEBUG:
                    print(f"  MAC_MAC matched. Capitlizing: {word}")
                tc_line.append(
                    f"{match.group(1).capitalize()}{match.group(2).capitalize()}"
                )
                continue

            hyphenated = []
            for item in word.split("-"):
                hyphenated.append(
                    CAPFIRST.sub(lambda m: m.group(0).upper(), item)
                )
            tc_line.append("-".join(hyphenated))

        result = " ".join(tc_line)

        result = SMALL_FIRST.sub(
            lambda m: f"{m.group(1)}{m.group(2).capitalize()}", result
        )

        result = SMALL_LAST.sub(lambda m: m.group(0).capitalize(), result)
        result = SUBPHRASE.sub(
            lambda m: f"{m.group(1)}{m.group(2).capitalize()}", result
        )

        processed.append(result)
        text = "\n".join(processed)

    # replace V. with v.
    text = re.sub(re.compile(r"\WV\.\W"), " v. ", text)

    return text


def harmonize(text):
    """Fixes case names so they are cleaner.

    Using a bunch of regex's, this function cleans up common data problems in
    case names. The following are currently fixed:
     - various forms of United States --> United States
     - The State --> State
     - vs. --> v.
     - et al --> Removed.
     - plaintiff, appellee, defendant and the like --> Removed.
     - No. and Nos. removed from beginning

    Lots of tests are in tests.py.
    """

    result = ""
    # replace vs. with v.
    text = re.sub(re.compile(r"\Wvs\.\W"), " v. ", text)

    # replace V. with v.
    text = re.sub(re.compile(r"\WV\.\W"), " v. ", text)

    # replace v with v.
    text = re.sub(re.compile(r" v "), " v. ", text)

    # and finally, vs with v.
    text = re.sub(re.compile(r" vs "), " v. ", text)

    # Remove the BAD_WORDS.
    text = text.split()
    cleaned_text = []
    for word in text:
        word = re.sub(BAD_WORDS, "", word)
        cleaned_text.append(word)
    text = " ".join(cleaned_text)

    # split on all ' v. ' and then deal with United States variations.
    text = text.split(" v. ")
    i = 1
    for frag in text:
        frag = frag.strip()
        if UNITED_STATES.match(frag):
            result += "United States"
        elif THE_STATE.match(frag):
            result += "State"
        else:
            # needed here, because we can't put "US" as a case-insensitive
            # word into the UNITED_STATES regex.
            frag = re.sub(re.compile(r"^US$"), "United States", frag)
            # no match
            result += frag

        if i < len(text):
            # More stuff coming; append v.
            result += " v. "
        i += 1

    # Remove the ET_AL words.
    result = re.sub(ET_AL, "", result)

    # Fix the No. and Nos.
    if result.startswith("No.") or result.startswith("Nos."):
        result = re.sub(r"^Nos?\.\s+", "", result)

    return clean_string(result)


def format_case_name(n):
    """Applies standard harmonization methods after normalizing with
    lowercase."""
    return titlecase(harmonize(n.lower()))


def get_court_object(raw_court, file_path, fallback=""):
    """Get the court object from a string. Searches through `state_pairs`.

    :param raw_court: A raw court string, parsed from an XML file.
    :param fallback: If fail to find one, will apply the regexes associated to
    this key in `SPECIAL_REGEXES`.
    """
    # this messes up for, e.g. 'St. Louis', but works for all others
    if "." in raw_court and "St." not in raw_court:
        j = raw_court.find(".")
        raw_court = raw_court[:j]
    # we need the comma to successfully match Superior Courts, the name of which
    # comes after the comma
    if "," in raw_court and "Superior Court" not in raw_court:
        j = raw_court.find(",")
        raw_court = raw_court[:j]
    for regex, value in state_pairs:
        if re.search(regex, raw_court):
            return value
    if fallback in SPECIAL_REGEXES:
        for regex, value in SPECIAL_REGEXES[fallback]:
            if re.search(regex, raw_court):
                return value
    folder = file_path.split("/documents")[0]
    if folder in FOLDER_DICT:
        return FOLDER_DICT[fallback]


def parse_file(file_path, court_fallback=""):
    """Parses a file, turning it into a correctly formatted dictionary, ready to be used by a populate script.

    :param file_path: A path the file to be parsed.
    :param court_fallback: A string used as a fallback in getting the court object.
        The regexes associated to its value in special_regexes will be used.
    """
    raw_info = get_text(file_path)
    if raw_info is None:
        return
    info = {
        "unpublished": raw_info["unpublished"],
        "file": os.path.splitext(os.path.basename(file_path))[0],
        "docket": "".join(raw_info.get("docket", [])) or None,
        "citations": raw_info.get("citation", []),
        "attorneys": "".join(raw_info.get("attorneys", [])) or None,
        "posture": "".join(raw_info.get("posture", [])) or None,
    }
    # throughout the process, collect all info about judges and at the end use it to populate info['judges']
    # get basic info
    # panel_text = ''.join(raw_info.get('panel', []))
    # if panel_text:
    #    judge_info.append(('Panel\n-----', panel_text))
    # get dates
    # print(raw_info.get('reporter_caption', []))
    caseyear = None
    if "citation" in raw_info:
        for x in raw_info["citation"]:
            if x.endswith(")"):
                caseyear = int(x[-5:-1])  # extract year from case_name_full
                # print(caseyear)
        if caseyear is None:
            print(raw_info["citation"])
    dates = raw_info.get("date", []) + raw_info.get("hearing_date", [])
    info["dates"] = parse_dates(dates, caseyear)

    # get case names
    # figure out if this case was heard per curiam by checking the first chunk of text in fields in which this is
    # usually indicated
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
                info["opinions"].append(
                    {
                        "opinion": "\n".join(last_texts),
                        "opinion_texts": last_texts,
                        "type": current_type,
                        "byline": opinion["byline"],
                    }
                )
                last_texts = []
                if current_type == "opinion":
                    info["judges"] = opinion["byline"]

        # if there are remaining texts without bylines, either add them to the last opinion of this type, or if there
        # are none, make a new opinion without an author
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
    # check if opinions were heard per curiam by checking if the first chunk of text in the byline or in
    #  any of its associated opinion texts indicate this
    for opinion in info["opinions"]:
        # if there's already an identified author, it's not per curiam
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
    # if this is an unpublished opinion, note this down and remove all <unpublished> tags
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
    try:
        root = ET.fromstring(file_string)
    except ET.ParseError:
        # these seem to be erroneously swapped quite often -- try to fix the misordered tags
        # file_string = file_string.replace('</footnote_body></block_quote>', '</block_quote></footnote_body>')
        # root = ET.fromstring(file_string)
        return
    for child in root.iter():
        # if this child is one of the ones identified by SIMPLE_TAGS, just grab its text

        if child.tag in SIMPLE_TAGS:
            # strip unwanted tags and xml formatting
            text = get_xml_string(child)
            for r in STRIP_REGEX:
                text = re.sub(r, "", text)
            text = re.sub(r"<.*?>", " ", text).strip()
            # put into a list associated with its tag
            # if child.tag == 'date':
            # print(text)
            # raise
            raw_info.setdefault(child.tag, []).append(text)
            continue
        for opinion_type in OPINION_TYPES:
            # c if this child is a byline, note it down and use it later
            if child.tag == f"{opinion_type}_byline":
                current_byline["type"] = opinion_type
                current_byline["name"] = get_xml_string(child)
                break
            # if this child is an opinion text blob, add it to an incomplete opinion and move into the info dict
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
    return raw_info


def parse_dates(raw_dates, caseyear):
    """Parses the dates from a list of string.
    Returns a list of lists of (string, datetime) tuples if there is a string before the date (or None).

    :param raw_dates: A list of (probably) date-containing strings
    :param caseyear: the year of the case (for checking)
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
                date = dparser.parse(raw_part, fuzzy=True).date()
            except:
                continue
            #            if caseyear is not None:
            #                if date.year > caseyear + 1 or date.year < caseyear - 2:
            #                    print(('Year problem:',date.year,raw_date,caseyear))
            #                    date = datetime(caseyear, date.month, date.day)

            if date.year < 1600 or date.year > 2020:
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
                inner_dates.append((clean_string(text), date))
            else:
                inner_dates.append((None, date))
        dates.append(inner_dates)
    return dates


def get_xml_string(e):
    """Returns a normalized string of the text in <element>.

    :param e: An XML element.
    """

    inner_string = re.sub(
        r"(^<%s\b.*?>|</%s\b.*?>$)" % (e.tag, e.tag),
        "",
        ET.tostring(e).decode(),
    )
    return inner_string.strip()


# dir_path = '/home/elliott/freelawmachine/flp/columbia_data/opinions'
# folders = glob(dir_path+'/*')
os.chdir("/home/elliott/freelawmachine/flp/columbia_data/opinions")

folders = glob("*")
folders.sort()

from collections import Counter

html_tab: Counter = Counter()

for folder in folders:
    if "_" in folder:
        continue
    print(folder)
    for path in file_generator(folder):
        # f = open(path).read()
        # x = f.count('<date>')
        # if x > 1:
        #    print(path)
        # break

        parsed = parse_file(path)
        if parsed is None:
            continue
        # print(parsed['dates'])
        newname = path.replace("/", "_")
        if len(parsed["dates"]) == 0:
            print(path)
            print(open(path).read(), file=open(f"_nodate/{newname}", "wt"))
            continue

        if len(parsed["dates"][0]) == 0:
            print(path)
#
#            print(open(path).read(), file=open('_failparse/'+newname,'wt'))
#

#        numops = len(parsed['opinions'])
#        if numops > 0:
#            for op in parsed['opinions']:
#                optext = op['opinion']
#                tags = re.findall('<.*?>',optext)
#                html_tab.update(tags)
#                #if '<block_quote>' in tags:
#                #    print(optext)
#                #    exit()
#
