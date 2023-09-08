"""
Command to merge opinions with columbia xml file

Merge using a csv file with cluster id and xml file path pointing to mounted directory and file path
docker-compose -f docker/courtlistener/docker-compose.yml exec cl-django python manage.py columbia_merge --csv-file /opt/courtlistener/cl/assets/media/test1.csv

Csv example:
cluster_id,filepath
825802,/opt/columbia/michigan/supreme_court_opinions/documents/d5a484f1bad20ba0.xml

Merge using a cluster id, it will work only if at least one opinion has a xml file path in local_path field
It requires passing the mounted directory path to the columbia xml files
docker-compose -f docker/courtlistener/docker-compose.yml exec cl-django python manage.py columbia_merge --cluster-id 2336478 --xml-dir /opt/columbia
"""
import csv
import os.path
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import dateutil.parser as dparser
from bs4 import BeautifulSoup, NavigableString, Tag
from django.db import transaction
from django.db.models import Q
from juriscraper.lib.string_utils import clean_string, harmonize, titlecase

from cl.corpus_importer.management.commands.harvard_opinions import (
    clean_docket_number,
)
from cl.corpus_importer.utils import similarity_scores
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_diff import get_cosine_similarity
from cl.people_db.lookup_utils import find_just_name
from cl.search.models import SOURCES, Docket, Opinion, OpinionCluster

VALID_CLUSTER_SOURCES = [
    SOURCES.COURT_WEBSITE,
    SOURCES.LAWBOX,
    SOURCES.PUBLIC_RESOURCE,
    SOURCES.HARVARD_CASELAW,
    SOURCES.LAWBOX_M_HARVARD,
]

ALREADY_MERGED_SOURCES = [
    SOURCES.COLUMBIA_ARCHIVE,
    SOURCES.COLUMBIA_M_COURT,
    SOURCES.COLUMBIA_M_LAWBOX_COURT,
    SOURCES.COLUMBIA_M_LAWBOX_RESOURCE,
    SOURCES.COLUMBIA_M_LAWBOX_COURT_RESOURCE,
    SOURCES.COLUMBIA_M_RESOURCE,
    SOURCES.COLUMBIA_M_COURT_RESOURCE,
    SOURCES.COLUMBIA_M_LAWBOX,
    SOURCES.COLUMBIA_ARCHIVE_M_HARVARD,
    SOURCES.COLUMBIA_M_LAWBOX_M_HARVARD,
]

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
    "opinion issued",
    "delivered",
    "rendered",
    "considered on briefs on",
    "opinion delivered and filed",
    "orally argued",
    "rendered on",
    "oral argument",
    "submitted on record and briefs",
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
UNKNOWN_TAGS = [
    "petition for review allowed",
    "affirmed",
    "reversed and remanded",
    "rehearing overruled",
    "review granted",
    "decision released",
    "transfer denied",
    "released for publication",
    "application to transfer denied",
    "amended",
    "reversed",
    "opinion on petition to rehear",
    "suggestion of error overruled",
    "cv",
    "case stored in record room",
    "met to file petition for review disposed granted",
    "rehearing granted",
    "opinion released",
    "permission to appeal denied by supreme court",
    "rehearing pending",
    "application for transfer denied",
    "effective date",
    "modified",
    "opinion modified",
    "transfer granted",
    "discretionary review denied",
    "application for leave to file second petition for rehearing denied",
    "final",
    "date of judgment entry on appeal",
    "petition for review pending",
    "writ denied",
    "rehearing filed",
    "as extended",
    "officially released",
    "appendix filed",
    "spring sessions",
    "summer sessions",
    "fall sessions",
    "winter sessions",
    "discretionary review denied by supreme court",
    "dissenting opinion",
    "en banc reconsideration denied",
    "answer returned",
    "refiled",
    "revised",
    "modified upon denial of rehearing",
    "session mailed",
    "reversed and remanded with instructions",
    "writ granted",
    "date of judgment entry",
    "preliminary ruling rendered",
    "amended on",
    "dissenting opinion filed",
    "concurring opinion filed",
    "memorandum dated",
    "mandamus denied on mandate",
    "updated",
    "date of judgment entered",
    "released and journalized",
    "submitted on",
    "case assigned",
    "opinion circulated for comment",
    "submitted on rehearing",
    "united states supreme court dismissed appeal",
    "answered",
    "reconsideration granted in part and as amended",
    "as amended on denial of rehearing",
    "reassigned",
    "as amended",
    "as corrected",
    "writ allowed",
    "released",
    "application for leave to appeal filed",
    "affirmed on appeal reversed and remanded",
    "as corrected",
    "withdrawn substituted and refiled",
    "answered",
    "released",
    "as modified and ordered published",
    "remanded",
    "concurring opinion added",
    "decision and journal entry dated",
    "memorandum filed",
    "as modified",
]


class OpinionMatchingException(Exception):
    """An exception for wrong matching opinions"""

    def __init__(self, message: str) -> None:
        self.message = message


class AuthorException(Exception):
    """Error found in author merger."""

    def __init__(self, message: str) -> None:
        self.message = message


class OpinionTypeException(Exception):
    """An exception for incorrect opinion types"""

    def __init__(self, message: str) -> None:
        self.message = message


class DocketSourceException(Exception):
    """An exception for wrong docket source"""

    def __init__(self, message: str) -> None:
        self.message = message


class ClusterSourceException(Exception):
    """An exception for wrong cluster source"""

    def __init__(self, message: str) -> None:
        self.message = message


class DateException(Exception):
    """Error found in date merger."""

    def __init__(self, message: str) -> None:
        self.message = message


def format_case_name(n):
    """Applies standard harmonization methods after normalizing with
    lowercase."""
    return titlecase(harmonize(n.lower()))


def match_text_lists(
    file_opinions_list: List[Any], cl_opinions_list: List[Any]
) -> dict[int, int]:
    """Generate matching lists above threshold
    :param file_opinions_list: Opinions from file
    :param cl_opinions_list: CL opinions
    :return: Matches if found or empty dict
    """
    # We import this here to avoid a circular import
    from cl.corpus_importer.management.commands.harvard_opinions import (
        compare_documents,
    )

    scores = similarity_scores(file_opinions_list, cl_opinions_list)

    matches = {}
    for i, row in enumerate(scores):
        j = row.argmax()  # type: ignore
        # Lower threshold for small opinions.
        if (
            get_cosine_similarity(file_opinions_list[i], cl_opinions_list[j])
            < 0.60
        ):
            continue
        percent_match = compare_documents(
            file_opinions_list[i], cl_opinions_list[j]
        )
        if percent_match < 60:
            continue
        matches[i] = j

    # Key is opinion position from file, Value is opinion position from cl opinion
    # e.g. matches {0: 1, 1: 2} 0 is file opinion and 1 in cl opinion, 1 is file
    # opinion and 2 is cl opinion
    return matches


def get_cl_opinion_content(cluster_id) -> tuple[str, list[dict]]:
    """Get the opinions content for a cluster object
    :param cluster_id: Cluster ID for a set of opinions
    :return: (xml path, list of extracted opinions)
    """
    cl_cleaned_opinions = []
    opinions_from_cluster = Opinion.objects.filter(cluster_id=cluster_id)
    xml_path = None

    for i, op in enumerate(opinions_from_cluster):
        if op.local_path and not xml_path:
            xml_path = str(op.local_path)
        content = None
        if len(op.html_with_citations) > 1:
            content = op.html_with_citations
        elif len(op.html_columbia) > 1:
            content = op.html_columbia
        elif len(op.html_lawbox) > 1:
            content = op.html_lawbox
        elif len(op.plain_text) > 1:
            content = op.plain_text
        elif len(op.html) > 1:
            content = op.html
        elif len(op.xml_harvard) > 1:
            content = op.xml_harvard
        if content:
            soup = BeautifulSoup(content, features="html.parser")
            prep_text = re.sub(
                r"[^a-zA-Z0-9 ]", "", soup.getText(separator=" ").lower()
            )
            prep_text = re.sub(" +", " ", prep_text)
            cl_cleaned_opinions.append(
                {
                    "id": op.id,
                    "byline": op.author_str,
                    "type": op.type,
                    "opinion": prep_text,
                }
            )

    return xml_path, cl_cleaned_opinions


def read_xml(xml_filepath: str) -> dict:
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
                    # Content not inside _text tag, we store it
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

    # only first opinion with "opinion" type is a lead opinion, the next opinion with
    # "opinion" type is an addendum
    lead = False
    for op in opinions:
        op_type = op.get("type")
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
                            # The element is not tagged, it is just a text
                            # string
                            r.next_sibling.extract()
                    r.extract()

        # We use space as a separator to add a space when we have one tag
        # next to other without a space, ee try to remove double spaces
        data[tag] = [
            re.sub(" +", " ", found_tag.get_text(separator=" ").strip())
            for found_tag in found_tags
        ]

        if tag == "citation":
            # Remove duplicated citations,
            data[tag] = list(set(data[tag]))

    # Get syllabus from file
    data["syllabus"] = "\n".join(
        [s.decode_contents() for s in soup.findAll("syllabus")]
    )

    # Add opinions to dict
    data["opinions"] = opinions

    # Add file path to dict
    data["file"] = xml_filepath

    # Join fields values and set model field names
    data["docket"] = "".join(data.get("docket", [])) or None
    data["attorneys"] = "".join(data.get("attorneys", [])) or None
    data["posture"] = "".join(data.get("posture", [])) or None
    data["case_name_full"] = (
        format_case_name("".join(data.get("caption", []))) or ""
    )
    data["case_name"] = (
        format_case_name("".join(data.get("reporter_caption", []))) or ""
    )

    return data


def convert_columbia_html(text):
    """Convert xml tags to html tags
    :param text: Text to convert to html
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


def convert_columbia_opinion(text: str, opinion_index: int) -> str:
    """Convert xml tags to html tags and process additional data from opinions
    like footnotes,
    :param text: Text to convert to html
    :param opinion_index: opinion index from a list of all opinions
    :return: converted text
    """

    text = convert_columbia_html(text)

    # grayed-out page numbers
    text = re.sub("<page_number>", ' <span class="star-pagination">*', text)
    text = re.sub("</page_number>", "</span> ", text)

    # footnotes
    foot_references = re.findall(
        "<footnote_reference>.*?</footnote_reference>", text
    )

    for ref in foot_references:
        if (match := re.search(r"[\*\d]+", ref)) is not None:
            f_num = match.group()
        elif (match := re.search(r"\[fn(.+)\]", ref)) is not None:
            f_num = match.group(1)
        else:
            f_num = None
        if f_num:
            rep = f'<sup id="op{opinion_index}-ref-fn{f_num}"><a href="#op{opinion_index}-fn{f_num}">{f_num}</a></sup>'
            text = text.replace(ref, rep)

    # Add footnotes to opinion
    footnotes = re.findall("<footnote_body>.[\s\S]*?</footnote_body>", text)
    for fn in footnotes:
        content = re.search("<footnote_body>(.[\s\S]*?)</footnote_body>", fn)
        if content:
            rep = r'<div class="footnote">%s</div>' % content.group(1)
            text = text.replace(fn, rep)

    # Replace footnote numbers
    foot_numbers = re.findall("<footnote_number>.*?</footnote_number>", text)
    for ref in foot_numbers:
        if (match := re.search(r"[\*\d]+", ref)) is not None:
            f_num = match.group()
        elif (match := re.search(r"\[fn(.+)\]", ref)) is not None:
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

    return text


def update_matching_opinions(
    matches: dict, cl_cleaned_opinions: list, columbia_opinions: list
) -> None:
    """Update matching opinions
    :param matches: dict with matching position from cl and columbia opinions
    :param cl_cleaned_opinions: list of cl opinions
    :param columbia_opinions: list of columbia opinions
    :return: None
    """
    for columbia_pos, cl_pos in matches.items():
        # TODO verify order correct
        file_opinion = columbia_opinions[columbia_pos]  # type: dict
        file_byline = file_opinion.get("byline")
        cl_opinion = cl_cleaned_opinions[cl_pos]
        opinion_id_to_update = cl_opinion.get("id")
        # opinion_id_byline = cl_opinion.get("byline")

        op = Opinion.objects.get(id=opinion_id_to_update)
        author_str = ""
        if file_byline:
            # Prettify the name a bit
            author_str = titlecase(find_just_name(file_byline.strip(":")))
        if op.author_str == "":
            # We have an empty author name
            if author_str:
                # Store the name extracted from the author tag
                op.author_str = author_str
        else:
            if author_str:
                if find_just_name(op.author_str) != find_just_name(author_str):
                    raise AuthorException(f"Authors don't match - log error")
                elif any(s.isupper() for s in op.author_str.split(",")):
                    # Some names are uppercase, update with processed names
                    op.author_str = author_str

        converted_text = convert_columbia_opinion(
            file_opinion["opinion"], columbia_pos
        )
        op.html_columbia = str(converted_text)
        op.save()


def map_and_merge_opinions(
    cluster_id: int,
    cl_cleaned_opinions: list[dict],
    columbia_opinions: list[dict],
):
    """Map and merge opinion data
    :param cluster_id: Cluster id
    :param cl_cleaned_opinions: list of cl opinions
    :param columbia_opinions: list of columbia opinions from file
    """

    if len(columbia_opinions) == len(cl_cleaned_opinions):
        matches = match_text_lists(
            [op.get("opinion") for op in columbia_opinions],
            [op.get("opinion") for op in cl_cleaned_opinions],
        )
        if len(matches) == len(columbia_opinions):
            update_matching_opinions(
                matches, cl_cleaned_opinions, columbia_opinions
            )
        else:
            raise OpinionMatchingException("Failed to match opinions")

    else:
        # Skip creating new opinion cluster due to differences between data
        logger.info(
            msg=f"Skip merging mismatched opinions on cluster: {cluster_id}"
        )


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


def fetch_columbia_metadata(columbia_data) -> Dict[str, Any]:
    data = {}

    fields = [
        "syllabus",
        "attorneys",
        "posture",
    ]

    dates = columbia_data.get("date", []) + columbia_data.get(
        "hearing_date", []
    )
    parsed_dates = parse_dates(dates)

    current_year = date.today().year

    date_filed = date_argued = date_reargued = date_reargument_denied = None
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
            else:
                unknown_date = date_info[1]
                if date_info[0] not in UNKNOWN_TAGS:
                    logger.info(
                        f"Found unknown date tag {date_info[0]} with date {date_info[1]} in file {columbia_data['file']}"
                    )

    # the main date (used for date_filed in OpinionCluster) and panel dates
    # (used for finding judges) are ordered in terms of which type of dates
    # best reflect them
    main_date = (
        date_filed
        or date_argued
        or date_reargued
        or date_reargument_denied
        or unknown_date
    )
    if main_date is None:
        raise DateException(
            f"Failed to get a date for {columbia_data['file']}"
        )

    data["date_filed"] = date_filed

    for k, v in columbia_data.items():
        if k in fields:
            data[k] = v if v else ""
    return data


def combine_non_overlapping_data(
    cluster: OpinionCluster, columbia_data: dict
) -> dict[str, Tuple]:
    """Combine non overlapping data and return dictionary of data for merging

    :param cluster: Cluster to merge
    :param columbia_data: The columbia data as json
    :return: Optional dictionary of data to continue to merge
    """
    all_data = fetch_columbia_metadata(columbia_data)
    changed_values_dictionary: dict[str, Tuple] = {}
    to_update: dict[str, Any] = {}
    for key, value in all_data.items():
        cl_value = getattr(cluster, key)
        if not cl_value:
            # Value is empty for key, we can add it directly to the object
            to_update[key] = value
        else:
            if value != cl_value:
                # We have different values, update dict
                changed_values_dictionary[key] = (value, cl_value)

    if to_update:
        # Update all fields at once
        OpinionCluster.objects.filter(id=cluster.id).update(**to_update)

    return changed_values_dictionary


def merge_docket_numbers(cluster: OpinionCluster, docket_number: str) -> None:
    """Merge docket number
    :param cluster: The cluster of the merging item
    :param docket_number: The columbia docket number
    :return: None
    """
    cl_docket = cluster.docket
    columbia_clean_docket = clean_docket_number(docket_number)

    if cl_docket.docket_number:
        # Check if docket number exists
        cl_clean_docket = clean_docket_number(cl_docket.docket_number)
        if (
            cl_clean_docket in columbia_clean_docket
            and cl_docket.docket_number != columbia_clean_docket
        ):
            cl_docket.docket_number = columbia_clean_docket
            cl_docket.save()
        else:
            # Check if their relatively similar and if so save the columbia one
            # if its longer
            similarity = get_cosine_similarity(
                cl_clean_docket, columbia_clean_docket
            )
            if similarity > 0.8:
                if len(columbia_clean_docket) > len(cl_clean_docket):
                    cl_docket.docket_number = columbia_clean_docket
                    cl_docket.save()
    else:
        # CL docket doesn't have a docket number, add the one from json file
        cl_docket.docket_number = columbia_clean_docket
        cl_docket.save()


def merge_case_names(
    cluster: OpinionCluster, columbia_data: Dict[str, Any]
) -> dict[str, Any]:
    """Merge case names
    :param cluster: The cluster of the merging item
    :param columbia_data: json data from columbia
    :return: None
    """
    columbia_case_name = titlecase(harmonize(columbia_data["case_name"]))
    columbia_case_name_full = titlecase(columbia_data["case_name_full"])
    cluster_case_name = titlecase(harmonize(cluster.case_name))
    cluster_case_name_full = titlecase(cluster.case_name_full)

    update_dict = {}
    # Case with full case names
    if not cluster_case_name_full and columbia_case_name_full:
        update_dict["case_name_full"] = columbia_case_name_full
        # Change stored value to new
        cluster_case_name_full = columbia_case_name_full
    elif cluster_case_name_full and columbia_case_name_full:
        if len(columbia_case_name_full) > len(cluster_case_name_full):
            # Select best case name based on string length
            update_dict["case_name_full"] = columbia_case_name_full
            # Change stored value to new
            cluster_case_name_full = columbia_case_name_full
    else:
        # We don't care if data is empty or both are empty
        pass

    # Case with abbreviated case names
    if not cluster_case_name and columbia_case_name:
        update_dict["case_name"] = columbia_case_name
        # Change stored value to new
        cluster_case_name = columbia_case_name
    elif cluster_case_name and columbia_case_name:
        if len(columbia_case_name) > len(cluster_case_name):
            # Select best case name based on string length
            update_dict["case_name"] = columbia_case_name
            # Change stored value to new
            cluster_case_name = columbia_case_name
    else:
        # We don't care if data is empty or both are empty
        pass

    if cluster_case_name_full and cluster_case_name:
        if len(cluster_case_name) > len(cluster_case_name_full):
            # Swap field values
            update_dict["case_name"] = cluster_case_name_full
            update_dict["case_name_full"] = cluster_case_name

    return update_dict


def merge_date_filed(
    cluster: OpinionCluster, columbia_data: dict
) -> dict[str, Any]:
    """Merge date filed
    :param cluster: The cluster of the merging item
    :param columbia_data: json data from columbia
    :return: None
    """

    columbia_date_filed = columbia_data.get("date_filed")
    cluster_date_filed = cluster.date_filed

    if columbia_date_filed:
        if cluster.docket.source == Docket.SCRAPER:
            # Give preference to columbia data
            if columbia_date_filed != cluster_date_filed:
                return {"date_filed": columbia_date_filed}

    return {}


def merge_long_fields(
    field_name: str,
    overlapping_data: Optional[Tuple[str, str]],
    cluster_id: int,
) -> dict[str, Any]:
    """Merge two long text fields
    :param field_name: Field name to update in opinion cluster
    :param overlapping_data: data to compare from columbia and courtlistener
    :param cluster_id: cluster id
    :return: None
    """
    if not overlapping_data:
        return {}

    columbia_data, cl_data = overlapping_data
    # Do some text comparison
    similarity = get_cosine_similarity(columbia_data, cl_data)
    if similarity < 0.9:
        # they are not too similar, choose the larger one
        if len(columbia_data) > len(cl_data):
            return {field_name: columbia_data}

    else:
        if similarity <= 0.5:
            logger.info(
                f"The content compared is very different. Cluster id: {cluster_id}"
            )
    return {}


def merge_strings(
    field_name: str, overlapping_data: Tuple[str, str]
) -> dict[str, Any]:
    """Compare two strings and choose the largest

    :param field_name: field name to update in opinion cluster
    :param overlapping_data: data to compare from columbia and courtlistener
    :return: None
    """
    if not overlapping_data:
        return {}

    columbia_data, cl_data = overlapping_data
    if len(columbia_data) > len(cl_data):
        return {field_name: columbia_data}

    return {}


def merge_overlapping_data(
    cluster: OpinionCluster, changed_values_dictionary: dict
) -> dict[str, Any]:
    """Merge overlapping data
    :param cluster: the cluster object
    :param changed_values_dictionary: the dictionary of data to merge
    :return: None
    """

    if not changed_values_dictionary:
        # Empty dictionary means that we don't have overlapping data
        return {}

    long_fields = ["syllabus", "posture"]

    data_to_update = {}

    for field_name in changed_values_dictionary.keys():
        if field_name in long_fields:
            data_to_update.update(
                merge_long_fields(
                    field_name,
                    changed_values_dictionary.get(field_name),
                    cluster.id,
                )
            )
        elif field_name == "attorneys":
            data_to_update.update(
                merge_strings(
                    field_name,
                    changed_values_dictionary.get(field_name, ""),
                )
            )
        else:
            logger.info(f"Field not considered in the process: {field_name}")

    return data_to_update


def update_docket_source(cluster: OpinionCluster) -> None:
    """Update docket source and complete
    :param cluster: the cluster object
    :return: None
    """
    docket = cluster.docket
    new_docket_source = Docket.COLUMBIA + docket.source
    if new_docket_source in [
        Docket.COLUMBIA,
        Docket.COLUMBIA_AND_RECAP,
        Docket.COLUMBIA_AND_SCRAPER,
        Docket.COLUMBIA_AND_RECAP_AND_SCRAPER,
        Docket.COLUMBIA_AND_IDB,
        Docket.COLUMBIA_AND_RECAP_AND_IDB,
        Docket.COLUMBIA_AND_SCRAPER_AND_IDB,
        Docket.COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB,
        Docket.HARVARD_AND_COLUMBIA,
    ]:
        # Source is limited to those options because those are the only
        # valid options when we sum the source with columbia source
        docket.source = new_docket_source
        docket.save()
    else:
        raise DocketSourceException(
            f"Unexpected docket source: {new_docket_source}"
        )


def update_cluster_source(cluster: OpinionCluster) -> None:
    """Update cluster source
    :param cluster: cluster object
    :return: None
    """
    new_cluster_source = SOURCES.COLUMBIA_ARCHIVE + cluster.source

    if new_cluster_source in [
        SOURCES.COLUMBIA_ARCHIVE,
        SOURCES.COLUMBIA_M_COURT,
        SOURCES.COLUMBIA_M_LAWBOX_COURT,
        SOURCES.COLUMBIA_M_LAWBOX_RESOURCE,
        SOURCES.COLUMBIA_M_LAWBOX_COURT_RESOURCE,
        SOURCES.COLUMBIA_M_RESOURCE,
        SOURCES.COLUMBIA_M_COURT_RESOURCE,
        SOURCES.COLUMBIA_M_LAWBOX,
        SOURCES.COLUMBIA_ARCHIVE_M_HARVARD,
    ]:
        cluster.source = new_cluster_source
        cluster.save()
    else:
        raise ClusterSourceException(
            f"Unexpected cluster source: {new_cluster_source}"
        )


def process_cluster(
    cluster_id: int,
    xml_dir: str = "",
    filepath: str = "",
    csv_file: bool = False,
):
    """Merge specified cluster id
    :param cluster_id: Cluster object id to merge
    :param xml_dir: path to mounted dir
    :param filepath: specified path to xml file
    :param csv_file: set to true if using a csv file
    """
    try:
        cluster = OpinionCluster.objects.get(pk=cluster_id)
    except OpinionCluster.DoesNotExist:
        logger.info(f"Cluster ID: {cluster_id} doesn't exist")
        return

    # Early abort
    if OpinionCluster.objects.filter(
        pk=cluster_id, source__in=ALREADY_MERGED_SOURCES
    ).exists():
        logger.info(f"Cluster ID: {cluster_id} already merged.")
        return
    if (
        OpinionCluster.objects.filter(pk=cluster_id)
        .filter(~Q(source__in=VALID_CLUSTER_SOURCES))
        .exists()
    ):
        logger.info(f"Cluster ID: {cluster_id} source not valid.")
        return

    xml_path, cl_cleaned_opinions = get_cl_opinion_content(cluster_id)

    if not xml_path and not csv_file:
        logger.info(
            f"Cluster ID: {cluster_id} doesn't have a local_path field."
        )
        return

    if not csv_file:
        if "/home/mlissner/columbia/opinions/" in xml_path:
            filepath = xml_path.replace(
                "/home/mlissner/columbia/opinions/", ""
            )
            # fix file path temporarily
            new_xml_filepath = os.path.join(xml_dir, filepath)
        else:
            logger.info(
                f"Can't fix xml file in: {xml_path} from an opinion from cluster ID: {cluster_id}"
            )
            return
    else:
        new_xml_filepath = filepath

    columbia_data = read_xml(new_xml_filepath)

    try:
        with transaction.atomic():
            map_and_merge_opinions(
                cluster_id, cl_cleaned_opinions, columbia_data["opinions"]
            )
            # Non overlapping data
            changed_values_dictionary = combine_non_overlapping_data(
                cluster, columbia_data
            )

            cluster.refresh_from_db()

            # docket number
            merge_docket_numbers(cluster, columbia_data["docket"])
            # case names
            case_names_to_update = merge_case_names(cluster, columbia_data)
            # date filed
            date_filed_to_update = merge_date_filed(cluster, columbia_data)
            # overlapping data
            overlapping_data_to_update = merge_overlapping_data(
                cluster, changed_values_dictionary
            )
            # TODO panel

            # Merge results
            data_to_update = (
                case_names_to_update
                | date_filed_to_update
                | overlapping_data_to_update
            )

            if data_to_update:
                OpinionCluster.objects.filter(id=cluster_id).update(
                    **data_to_update
                )

            # We need to refresh the object before trying to use it to
            # update the cluster source
            cluster.refresh_from_db()

            update_docket_source(cluster)
            update_cluster_source(cluster)
            logger.info(msg=f"Finished merging cluster: {cluster_id}")

    except AuthorException:
        logger.warning(msg=f"Author exception for cluster id: {cluster_id}")
    except OpinionMatchingException:
        logger.warning(
            msg=f"Opinions don't match for on cluster id: {cluster_id}"
        )
    except DocketSourceException:
        logger.warning(
            msg=f"Docket source exception related to cluster id: {cluster_id}"
        )
    except ClusterSourceException:
        logger.warning(
            msg=f"Cluster source exception for cluster id: {cluster_id}"
        )
    except DateException:
        logger.warning(
            msg=f"Date exception found in {new_xml_filepath} related to cluster id: {cluster_id}"
        )


def process_csv(csv_path):
    """
    Import xml files from a list of cluster ids in csv file
    :param csv_path: Absolute path to csv file
    """
    logger.info(f"Loading csv file at {csv_path}")

    with open(csv_path, mode="r", encoding="utf-8") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            cluster_id = row.get("cluster_id")
            filepath = row.get("filepath")
            if cluster_id and filepath:
                process_cluster(
                    cluster_id=cluster_id, filepath=filepath, csv_file=True
                )


class Command(VerboseCommand):
    help = "Merge columbia opinions"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--cluster-id",
            type=int,
            help="An individual cluster ID to merge",
            required=False,
        )

        parser.add_argument(
            "--csv-file",
            help="Csv file with cluster ids to merge.",
            required=False,
        )

        parser.add_argument(
            "--xml-dir",
            required=False,
            help="The absolute path to the directory with columbia xml files",
        )

    def handle(self, *args, **options) -> None:
        if options["csv_file"] and options["cluster_id"]:
            logger.info(
                "You can only select one option csv-file or cluster-id"
            )
            return

        if options["csv_file"]:
            if not os.path.exists(options["csv_file"]):
                logger.info("XML file doesn't exist")
                return
            process_csv(options["csv_file"])

        if options["cluster_id"] and not options["xml_dir"]:
            logger.info(
                "Argument --xml-dir required to read xml files from mounted directory with --cluster-id option"
            )
            return

        if options["cluster_id"]:
            process_cluster(
                cluster_id=options["cluster_id"], xml_dir=options["xml_dir"]
            )

        if not options["csv_file"] and not options["cluster_id"]:
            cluster_ids = (
                OpinionCluster.objects.filter(source__in=VALID_CLUSTER_SOURCES)
                .exclude(
                    Q(sub_opinions__local_path="")
                    | Q(sub_opinions__local_path=None)
                )
                .distinct("id")
                .values_list("id", flat=True)
            )

            for cluster_id in cluster_ids:
                process_cluster(
                    cluster_id=cluster_id, xml_dir=options["xml_dir"]
                )
