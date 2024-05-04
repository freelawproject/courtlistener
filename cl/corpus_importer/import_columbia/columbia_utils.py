import itertools
import re
from datetime import date
from typing import Any, Optional

import dateutil.parser as dparser
from bs4 import BeautifulSoup, NavigableString, Tag
from juriscraper.lib.string_utils import clean_string, harmonize, titlecase

from cl.people_db.lookup_utils import extract_judge_last_name

FILED_TAGS = [
    "filed",
    "opinion filed",
    "date",
    "order filed",
    "delivered and filed",
    "letter filed",
    "dated",
    "release date",
    "filing date",
    "filed date",
    "date submitted",
    "as of",
    "opinions filed",
    "filed on",
    "decision filed",
    "date delivered",
    "affirmed and opinion filed",
    "dismissed and opinion filed",
    "decided and entered",
    "memorandum opinion filed",
    "memorandum opinion delivered and filed",
    "granted",
    "affirmed",
    "submitted and decided",
    "affirmed and memorandum opinion filed",
    "memorandum filed",
    "modified opinion filed",
    "opinion modified and refiled",
    "opinion filed on",
    "opinion on merits filed",
    "opinion delivered and filed on",
    "order delivered and filed",
    "date filed",
    "opinion filed in",
    "affirmed opinion filed",
]
DECIDED_TAGS = ["decided", "date decided", "decided on", "decided date"]
ARGUED_TAGS = [
    "argued",
    "submitted",
    "submitted on briefs",
    "on briefs",
    "heard",
    "considered on briefs",
    "argued and submitted",
    "opinion",
    "opinions delivered",
    "opinion delivered",
    "assigned on briefs",
    "assigned on brief",
    "opinion issued",
    "delivered",
    "rendered",
    "considered on briefs on",
    "opinion delivered and filed",
    "orally argued",
    "rendered on",
    "oral argument",
    "submitted on record and briefs",
    "argued on",
    "on reargument",
]
REARGUE_DENIED_TAGS = [
    "reargument denied",
    "rehearing denied",
    "further rehearing denied",
    "as modified on denial of rehearing",
    "order denying rehearing",
    "petition for rehearing filed",
    "motion for rehearing filed",
    "rehearing denied to bar commission",
    "reconsideration denied",
    "denied",
    "review denied",
    "motion for rehearing and/or transfer to supreme court denied",
    "motion for reargument denied",
    "petition and crosspetition for review denied",
    "opinion modified and as modified rehearing denied",
    "motion for rehearing andor transfer to supreme court denied",
    "petition for rehearing denied",
    "leave to appeal denied",
    "rehearings denied",
    "motion for rehearing denied",
    "second rehearing denied",
    "petition for review denied",
    "appeal dismissed",
    "rehearing en banc denied",
    "rehearing and rehearing en banc denied",
    "order denying petition for rehearing",
    "all petitions for review denied",
    "petition for allowance of appeal denied",
    "opinion modified and rehearing denied",
    "as amended on denial of rehearing",
    "reh denied",
    "opinion dissenting from denial of rehearing",
]
REARGUE_TAGS = ["reargued", "reheard", "upon rehearing", "on rehearing"]
CERT_GRANTED_TAGS = [
    "certiorari granted",
    "petition and crosspetition for writ of certiorari granted",
]
CERT_DENIED_TAGS = [
    "certiorari denied",
    "certiorari quashed",
    "certiorari denied by supreme court",
    "petition for certiorari denied by supreme court",
]
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


def format_case_name(name: str) -> str:
    """Applies standard harmonization methods after normalizing with lowercase

    :param name: case name
    :return: title cased name
    """
    return titlecase(harmonize(name.lower()))


def is_opinion_published(soup: BeautifulSoup) -> bool:
    """Check if opinion is unpublished or published

    :param soup: The XML object
    :return: true if opinion is published
    """
    opinion_tag = soup.find("opinion")

    if opinion_tag:
        if opinion_tag.get("unpublished") == "true":
            return False
        if opinion_tag.find("unpublished"):
            return False
    return True


def fix_xml_tags(file_content: str) -> str:
    """Fix bad tags in xlm file

    :param file_content: raw content from xml file
    :return: fixed xml as string
    """

    # Sometimes opening and ending tag mismatch (e.g. ed7c6b39dcb29c9c.xml)
    file_content = file_content.replace(
        "</footnote_body></block_quote>", "</block_quote></footnote_body>"
    )
    # Fix opinion with invalid attribute
    if "<opinion unpublished=true>" in file_content:
        file_content = file_content.replace(
            "<opinion unpublished=true>", "<opinion unpublished='true'>"
        )
        file_content = file_content.replace("<unpublished>", "").replace(
            "</unpublished>", ""
        )
    return file_content


def read_xml_to_soup(filepath: str) -> BeautifulSoup:
    """Read the xml file and return a BeautifulSoup object

    :param filepath: path to xml file
    :return: BeautifulSoup object of parsed content
    """
    with open(filepath, "r", encoding="utf-8") as f:
        file_content = f.read()
        file_content = fix_xml_tags(file_content)

    return BeautifulSoup(file_content, "lxml")


def add_floating_opinion(
    opinions: list, floating_content: list, opinion_order: int
) -> list:
    """Create a new opinion item

    We have found floating opinions in bs object, we keep the opinion content as a
    new opinion

    :param opinions: a list with opinions found
    :param floating_content: content that is not in known non-opinion tags
    :param opinion_order: opinion position
    :return: updated list of opinions
    """
    op_type = "opinion"
    if opinions:
        if opinions[-1].get("type"):
            # Use type of previous opinion if exists
            op_type = opinions[-1].get("type")

    # Get rid of double spaces from floating content
    opinion_content = re.sub(
        " +", " ", "\n".join(floating_content)
    ).strip()  # type: str
    if opinion_content:
        opinions.append(
            {
                "opinion": opinion_content,
                "order": opinion_order,
                "byline": "",
                "type": op_type,
            }
        )
    return opinions


def extract_columbia_opinions(
    outer_opinion: BeautifulSoup,
) -> list[Optional[dict]]:
    """Get the opinions of the soup object

    We extract all possible opinions from BeautifulSoup, with and without
    author, and we create new opinions if floating content exists(content that
    is not explicitly defined within an opinion tag or doesn't have an author)

    :param outer_opinion: element containing all xml tags
    :return: list of opinion dicts
    """
    opinions: list = []
    floating_content = []
    order = 0

    # We iterate all content to look for all possible opinions
    for i, content in enumerate(outer_opinion):  # type: int, Tag
        if isinstance(content, NavigableString):
            # We found a raw string, store it
            floating_content.append(str(content))
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
                if floating_content:
                    # We have found an opinion, but there is floating
                    # content, we create a dict with the opinion using the
                    # floating content with default type = "opinion"
                    opinions = add_floating_opinion(
                        opinions, floating_content, order
                    )
                    floating_content = []

                byline = content.find_previous_sibling()
                opinion_author = ""
                if byline and "_byline" in byline.name:
                    opinion_author = byline.get_text()

                opinion_content = re.sub(
                    " +", " ", content.decode_contents()
                ).strip()
                if opinion_content:
                    # Now we create a dict with current opinion
                    opinions.append(
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
                    # We store content that is not inside _text tag and is
                    # not in one of the known non-opinion tags
                    floating_content.append(str(content))

    # Combine the new content into another opinion. great.
    if floating_content:
        # If we end to go through all the found opinions and if we still
        # have floating content out there, we create a new opinion with the
        # last type of opinion
        opinions = add_floating_opinion(opinions, floating_content, order)
    return opinions


def merge_opinions(
    opinions: list, content: list, current_order: int
) -> tuple[list, int]:
    """Merge last and previous opinion if possible

    We try merge last and previous opinion to if are the same type or create a new
    opinion if merge is not possible

    :param opinions: list of opinions that is being updated constantly
    :param content: list of opinions without an author
    :param current_order: opinion position
    :return: updated list of opinions
    """

    # We check if the previous stored opinion matches the type of the
    # content, and we store the opinion dict temporary
    relevant_opinions = (
        [opinions[-1]]
        if opinions and opinions[-1]["type"] == content[0].get("type")
        else []
    )

    if relevant_opinions:
        relevant_opinions[-1]["opinion"] += "\n" + "\n".join(
            [f.get("opinion") for f in content if f.get("opinion")]
        )

    else:
        # No relevant opinions found, create a new opinion with the content
        opinion_content = "\n".join(
            [f.get("opinion") for f in content if f.get("opinion")]
        )
        new_opinion = {
            "byline": None,
            "type": content[0].get("type"),
            "opinion": opinion_content,
            "order": current_order,
            "per_curiam": is_per_curiam_opinion(opinion_content, None),
        }
        opinions.append(new_opinion)
        current_order = current_order + 1

    return opinions, current_order


def is_per_curiam_opinion(
    content: Optional[str], byline: Optional[str]
) -> bool:
    """Check if opinion author is per curiam

    :param content: opinion content
    :param byline: opinion text author
    :return: True if opinion author is per curiam
    """
    if byline and "per curiam" in byline[:1000].lower():
        return True
    if content and "per curiam" in content[:1000].lower():
        return True
    return False


def process_extracted_opinions(extracted_opinions: list) -> list:
    """Process all extracted opinions from columbia xml

    We read the extracted data in extract_opinions function to merge all
    possible floating opinions (it is not explicitly defined within an opinion
    tag or doesn't have an author)

    :param extracted_opinions: list of opinions obtained from xml file
    :return: a list with extracted and processed opinions
    """

    opinions: list = []
    authorless_content = []
    order = 0

    for i, found_content in enumerate(extracted_opinions, start=1):
        byline = found_content.get("byline")
        if not byline:
            # Opinion has no byline, store opinion content
            authorless_content.append(found_content)

        if byline:
            # Opinion has byline, get opinion type and content
            opinion_type = found_content.get("type")
            opinion_content = found_content.get("opinion", "")
            # Store content that doesn't match the current opinion type
            alternative_authorless_content = [
                content
                for content in authorless_content
                if content.get("type") != opinion_type
            ]
            # Keep content that matches the current type
            authorless_content = [
                op_content
                for op_content in authorless_content
                if op_content.get("type") == opinion_type
            ]

            if alternative_authorless_content:
                # Keep floating text that are not from the same type,
                # we need to create a separate opinion for those,
                # for example: in 2713f39c5a8e8684.xml we have an opinion
                # without an author, and the next opinion with an author is
                # a dissent opinion, we can't combine both
                opinions, order = merge_opinions(
                    opinions, alternative_authorless_content, order
                )

            opinion_content = (
                "\n".join(
                    [
                        f.get("opinion")
                        for f in authorless_content
                        if f.get("type") == opinion_type
                    ]
                )
                + "\n\n"
                + opinion_content
            )

            # Add new opinion
            new_opinion = {
                "byline": byline,
                "type": opinion_type,
                "opinion": opinion_content,
                "order": order,
                "per_curiam": is_per_curiam_opinion(opinion_content, byline),
            }

            opinions.append(new_opinion)
            order = order + 1
            authorless_content = []

        if len(extracted_opinions) == i and authorless_content:
            # If is the last opinion, and we still have opinions without
            # byline, create an opinion without an author and the contents
            # that couldn't be merged
            opinions, order = merge_opinions(
                opinions, authorless_content, order
            )

    return opinions


def fix_reporter_caption(found_tags) -> None:
    """Remove unnecessary information from reporter_caption tag

    The reporter_caption may contain the location, and we need to remove it
    to make the name cleaner e.g. Tex.App.-Ft.Worth [2d Dist.] 2002

    :param found_tags: a list of found tags
    :return: None
    """
    for found_tag in found_tags:
        # Remove inner <citation> and <page_number> tags and content
        extra_tags_to_remove = found_tag.findAll(["citation", "page_number"])
        if extra_tags_to_remove:
            for r in extra_tags_to_remove:
                if r.next_sibling:
                    if isinstance(r.next_sibling, NavigableString):
                        # The element is not tagged, it is just a text
                        # string
                        r.next_sibling.extract()
                if r.name == "citation":
                    # Extract and insert citation tag before
                    # reporter_caption tag
                    citation = r.extract()
                    found_tag.insert_before(citation)
                    continue
                r.extract()


def fetch_simple_tags(soup: BeautifulSoup, tag_name: str) -> list:
    """Find data for specified tag name

    :param soup: bs element containing all xml tags
    :param tag_name: xml tag name to find
    :return: a list containing the data found using tag_name
    """
    tag_data = []
    if tag_name in SIMPLE_TAGS:
        found_tags = soup.findAll(tag_name)

        if tag_name == "reporter_caption":
            fix_reporter_caption(found_tags)

        # We use space as a separator to add a space when we have one tag
        # next to other without a space
        tag_data = [
            found_tag.get_text(separator=" ").strip()
            for found_tag in found_tags
        ]

        if tag_name in ["attorneys", "posture"]:
            # Replace multiple line breaks in this specific fields
            tag_data = [re.sub("\n+", " ", c) for c in tag_data]

        if tag_name == "reporter_caption":
            # Remove the last comma from the case name
            tag_data = [c.rstrip(",") for c in tag_data]

        tag_data = [re.sub(" +", " ", c) for c in tag_data]

        if tag_name == "citation":
            # Remove duplicated citations
            tag_data = list(set(tag_data))

    return tag_data


def convert_columbia_html(text: str, opinion_index: int) -> str:
    """Convert opinion data to html

    Convert xml tags to html tags and process additional data from opinions
    like footnotes

    :param text: Text to convert to html
    :param opinion_index: opinion index from a list of all opinions
    :return: converted text
    """
    conversions = [
        ("italic", "em"),
        ("block_quote", "blockquote"),
        ("bold", "strong"),
        ("underline", "u"),
        ("strikethrough", "strike"),
        ("superscript", "sup"),
        ("subscript", "sub"),
        ("heading", "h3"),
        ("table", "pre"),
    ]

    for pattern, replacement in conversions:
        text = re.sub(f"<{pattern}>", f"<{replacement}>", text)
        text = re.sub(f"</{pattern}>", f"</{replacement}>", text)

        # grayed-out page numbers
        text = re.sub(
            "<page_number>", ' <span class="star-pagination">*', text
        )
        text = re.sub("</page_number>", "</span> ", text)

        # footnotes
        foot_references = re.findall(
            "<footnote_reference>.*?</footnote_reference>", text
        )

        # We use opinion index to ensure that all footnotes are linked to the
        # corresponding opinion
        for ref in foot_references:
            if (match := re.search(r"[*\d]+", ref)) is not None:
                f_num = match.group()
            elif (match := re.search(r"\[fn(.+)]", ref)) is not None:
                f_num = match.group(1)
            else:
                f_num = None
            if f_num:
                rep = f'<sup id="op{opinion_index}-ref-fn{f_num}"><a href="#op{opinion_index}-fn{f_num}">{f_num}</a></sup>'
                text = text.replace(ref, rep)

        # Add footnotes to opinion
        footnotes = re.findall(
            r"<footnote_body>.[\s\S]*?</footnote_body>", text
        )
        for fn in footnotes:
            content = re.search(
                r"<footnote_body>(.[\s\S]*?)</footnote_body>", fn
            )
            if content:
                rep = rf'<div class="footnote">{content.group(1)}</div>'
                text = text.replace(fn, rep)

        # Replace footnote numbers
        foot_numbers = re.findall(
            r"<footnote_number>.*?</footnote_number>", text
        )
        for ref in foot_numbers:
            if (match := re.search(r"[*\d]+", ref)) is not None:
                f_num = match.group()
            elif (match := re.search(r"\[fn(.+)]", ref)) is not None:
                f_num = match.group(1)
            else:
                f_num = None
            if f_num:
                rep = (
                    rf'<sup id="op{opinion_index}-fn%s"><a href="#op{opinion_index}-ref-fn%s">%s</a></sup>'
                    % (
                        f_num,
                        f_num,
                        f_num,
                    )
                )
                text = text.replace(ref, rep)

    # Make nice paragraphs. This replaces double newlines with paragraphs, then
    # nests paragraphs inside blockquotes, rather than vice versa. The former
    # looks good. The latter is bad.
    text = f"<p>{text}</p>"
    text = re.sub(r"</blockquote>\s*<blockquote>", "\n\n", text)
    text = re.sub("\n\n", "</p>\n<p>", text)
    text = re.sub("\n  ", "</p>\n<p>", text)
    text = re.sub(r"<p>\s*<blockquote>", "<blockquote><p>", text, re.M)
    text = re.sub("</blockquote></p>", "</p></blockquote>", text, re.M)

    return text


def parse_dates(
    raw_dates: list[str],
) -> list[list[tuple[Any, date] | tuple[None, date]]]:
    """Parses the dates from a list of string.

    :param raw_dates: A list of (probably) date-containing strings
    :return: Returns a list of lists of (string, datetime) tuples if there is
    a string before the date (or None).
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


def find_dates_in_xml(soup: BeautifulSoup) -> dict:
    """Find and extract all possible dates obtained from xml file

    :param soup: BeautifulSoup object containing all xml tags
    :return: dict with found dates
    """

    found_dates = fetch_simple_tags(soup, "date") + fetch_simple_tags(
        soup, "hearing_date"
    )
    parsed_dates = parse_dates(found_dates)
    current_year = date.today().year
    date_filed = date_argued = date_reargued = date_reargument_denied = (
        date_cert_granted
    ) = date_cert_denied = None
    unknown_date = None

    for date_cluster in parsed_dates:
        for date_info in date_cluster:
            # check for any dates that clearly aren't dates
            if date_info[1].year < 1600 or date_info[1].year > current_year:
                continue
            # check for untagged dates that will be assigned to date_filed
            if date_info[0] is None:
                date_filed = date_info[1]
                continue
            # try to figure out what type of date it is based on its tag string
            if date_info[0] in FILED_TAGS:
                date_filed = date_info[1]
            elif date_info[0] in DECIDED_TAGS:
                if not date_filed:
                    date_filed = date_info[1]
            elif date_info[0] in ARGUED_TAGS:
                date_argued = date_info[1]
            elif date_info[0] in REARGUE_TAGS:
                date_reargued = date_info[1]
            elif date_info[0] in REARGUE_DENIED_TAGS:
                date_reargument_denied = date_info[1]
            elif date_info[0] in CERT_GRANTED_TAGS:
                date_cert_granted = date_info[1]
            elif date_info[0] in CERT_DENIED_TAGS:
                date_cert_denied = date_info[1]
            else:
                unknown_date = date_info[1]

    # panel_date is used for finding judges, dates are ordered in terms of
    # which type of dates best reflect them
    panel_date = (
        date_argued
        or date_reargued
        or date_reargument_denied
        or date_filed
        or unknown_date
    )

    return {
        "date_filed": date_filed,
        "panel_date": panel_date,
        "date_cert_granted": date_cert_granted,
        "date_cert_denied": date_cert_denied,
        "date_argued": date_argued,
        "date_reargued": date_reargued,
        "date_reargument_denied": date_reargument_denied,
    }


def find_judges(opinions=None) -> str:
    """Find judges from opinions

    :param opinions: a list that contains all opinions as dict elements
    :return: list of judges
    """
    if opinions is None:
        opinions = []
    judges = []
    for op in opinions:
        op_byline = op.get("byline")
        if op_byline:
            judge_name = extract_judge_last_name(op_byline)
            if judge_name not in judges:
                judges.append(judge_name)

    judge_list = list(itertools.chain.from_iterable(judges))
    judge_list = list(map(titlecase, judge_list))
    return ", ".join(sorted(set(judge_list)))


def map_opinion_types(opinions=None) -> None:
    """Map opinion type to model field choice

    :param opinions: a list that contains all opinions as dict elements
    :return: None
    """

    if opinions is None:
        opinions = []
    lead = False
    for op in opinions:
        op_type = op.get("type")
        # Only first opinion with "opinion" type is a lead opinion, the next
        # opinion with "opinion" type is an addendum
        if not lead and op_type and op_type == "opinion":
            lead = True
            op["type"] = "020lead"
            continue
        elif lead and op_type and op_type == "opinion":
            op["type"] = "050addendum"
        elif op_type and op_type == "dissent":
            op["type"] = "040dissent"
        elif op_type and op_type == "concurrence":
            op["type"] = "030concurrence"
