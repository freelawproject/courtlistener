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
import itertools
import os.path
import re
import sys
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Optional

from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup, NavigableString, Tag
from django.db import transaction
from juriscraper.lib.string_utils import harmonize, titlecase

from cl.corpus_importer.import_columbia.columbia_utils import (
    ARGUED_TAGS,
    CERT_DENIED_TAGS,
    CERT_GRANTED_TAGS,
    DECIDED_TAGS,
    FILED_TAGS,
    REARGUE_DENIED_TAGS,
    REARGUE_TAGS,
    UNKNOWN_TAGS,
    convert_columbia_html,
    parse_dates,
)
from cl.corpus_importer.management.commands.harvard_opinions import (
    clean_docket_number,
)
from cl.corpus_importer.utils import (
    AuthorException,
    ClusterSourceException,
    DateException,
    DocketSourceException,
    JudgeException,
    OpinionMatchingException,
    OpinionTypeException,
    similarity_scores,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_diff import get_cosine_similarity
from cl.people_db.lookup_utils import (
    extract_judge_last_name,
    find_all_judges,
    find_just_name,
    lookup_judges_by_last_name_list,
)
from cl.people_db.models import Person
from cl.search.models import SOURCES, Docket, Opinion, OpinionCluster

VALID_UPDATED_DOCKET_SOURCES = [
    Docket.COLUMBIA,
    Docket.COLUMBIA_AND_RECAP,
    Docket.COLUMBIA_AND_SCRAPER,
    Docket.COLUMBIA_AND_RECAP_AND_SCRAPER,
    Docket.COLUMBIA_AND_IDB,
    Docket.COLUMBIA_AND_RECAP_AND_IDB,
    Docket.COLUMBIA_AND_SCRAPER_AND_IDB,
    Docket.COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB,
    Docket.HARVARD_AND_COLUMBIA,
    Docket.COLUMBIA_AND_RECAP_AND_HARVARD,
    Docket.COLUMBIA_AND_SCRAPER_AND_HARVARD,
    Docket.COLUMBIA_AND_RECAP_AND_SCRAPER_AND_HARVARD,
    Docket.COLUMBIA_AND_IDB_AND_HARVARD,
    Docket.COLUMBIA_AND_RECAP_AND_IDB_AND_HARVARD,
    Docket.COLUMBIA_AND_SCRAPER_AND_IDB_AND_HARVARD,
    Docket.COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD,
]


VALID_MERGED_SOURCES = [
    key
    for key in dict(SOURCES.NAMES).keys()
    if SOURCES.COLUMBIA_ARCHIVE in key
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
    """Applies standard harmonization methods after normalizing with
    lowercase.
    :param name: case name
    :return: title cased name
    """
    return titlecase(harmonize(name.lower()))


def match_text_lists(
    file_opinions_list: list[Any], cl_opinions_list: list[Any]
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
        # Remove non-alphanumeric and non-whitespace characters from lowercased text,
        # this tries to make both texts in equal conditions to prove if both are
        # similar or equal
        file_opinion = re.sub(
            r"[^a-zA-Z0-9 ]", "", file_opinions_list[i].lower()
        )
        cl_opinion = re.sub(r"[^a-zA-Z0-9 ]", "", cl_opinions_list[j].lower())

        # NOTE: get_cosine_similarity works great when both texts are almost the same
        # with very small variations
        cosine_sim = get_cosine_similarity(file_opinion, cl_opinion)
        # NOTE: compare_documents works good when the opinion from the file is a
        # subset of the opinion in CL, the percentage represents how much of the
        # opinion of the file is in the opinion from cl (content in cl opinion can
        # have other data in the body like posture, attorneys, etc. e.g. in cluster
        # id: 7643871 we have the posture and the opinion text but in the xml file we
        # only have the opinion text, cosine_sim: 0.1639075094124459 and
        # percent_match: 73)
        percent_match = compare_documents(file_opinion, cl_opinion)

        # Sometimes one algorithm performs better than the other, this is due to some
        # additional text, such as editor's notes, or the author, page number or posture
        # added to the opinion
        if cosine_sim < 0.60 and percent_match < 60:
            continue

        matches[i] = j

    # Key is opinion position from file, Value is opinion position from cl opinion
    # e.g. matches {0: 1, 1: 2} 0 is file opinion and 1 in cl opinion, 1 is file
    # opinion and 2 is cl opinion
    return matches


def clean_opinion_content(content: str, harvard_content: bool) -> str:
    """Strip all non-alphanumeric characters
    :param content: content from opinion
    :param harvard_content: true if content is from harvard
    :return: cleaned content
    """
    soup = BeautifulSoup(content, features="html.parser")

    if harvard_content:
        for op in soup.select("opinion"):
            # Remove any author tag inside opinion
            for extra in op.find_all(["author"]):
                extra.extract()

    prep_text = re.sub(
        r"[^a-zA-Z0-9 ]", "", soup.getText(separator=" ").lower()
    )
    prep_text = re.sub(" +", " ", prep_text)
    return prep_text


def get_cl_opinion_content(
    cluster_id: int,
) -> tuple[Optional[str], list[dict[Any, Any]]]:
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
        harvard_content = False
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
            harvard_content = True
        if content:
            prep_text = clean_opinion_content(
                content, harvard_content=harvard_content
            )
            cl_cleaned_opinions.append(
                {
                    "id": op.id,
                    "byline": op.author_str,
                    "type": op.type,
                    "opinion": prep_text,
                }
            )

    return xml_path, cl_cleaned_opinions


def fix_xml_tags(xml_filepath: str) -> tuple[str, bool]:
    """This function fixes the bad tags in columbia xml files
    :param xml_filepath: path to xml file
    :return: string with content, bool that indicates if opinion is unpublished or not
    """
    with open(xml_filepath, "r", encoding="utf-8") as f:
        file_content = f.read()

        # Sometimes opening and ending tag mismatch (e.g. ed7c6b39dcb29c9c.xml)
        file_content = file_content.replace(
            "</footnote_body></block_quote>", "</block_quote></footnote_body>"
        )

        # Fix opinion with invalid attribute
        if "<opinion unpublished=true>" in file_content:
            file_content = file_content.replace(
                "<opinion unpublished=true>", "<opinion>"
            )
            file_content = file_content.replace("<unpublished>", "").replace(
                "</unpublished>", ""
            )

            return file_content, True

    return file_content, False


def read_xml_file(xml_filepath: str) -> dict:
    """Read the columbia xml file and convert the data into a dict
    :param xml_filepath: path of xml file
    :return: dict with data
    """

    data: dict = {"unpublished": False}

    file_content, data["unpublished"] = fix_xml_tags(xml_filepath)

    soup = BeautifulSoup(file_content, "lxml")

    # Find the outer <opinion> tag to have all elements inside
    find_opinion = soup.find("opinion")

    step_one_opinions: list = []
    opinions: list = []
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

                        # default type = "opinion"
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
            # If we end to go through all the found opinions and if we still have
            # floating content out there, we create a new opinion with the last type
            # of opinion

            # default type = "opinion"
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

    data["judges"] = []
    # only first opinion with "opinion" type is a lead opinion, the next opinion with
    # "opinion" type is an addendum
    lead = False
    for op in opinions:
        op_type = op.get("type")
        op_byline = op.get("byline")
        if op_byline:
            data["judges"].append(extract_judge_last_name(op_byline))
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
            # Remove duplicated citations,
            data[tag] = list(set(data[tag]))

    dates = data.get("date", []) + data.get("hearing_date", [])
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
            elif date_info[0] in CERT_GRANTED_TAGS:
                # This date is stored in Docket, and we are not updating docket data,
                # ignore date
                pass
            elif date_info[0] in CERT_DENIED_TAGS:
                # This date is stored in Docket, and we are not updating docket data,
                # ignore date
                pass
            else:
                unknown_date = date_info[1]
                if date_info[0] not in UNKNOWN_TAGS:
                    logger.info(
                        f"Found unknown date tag {date_info[0]} with date {date_info[1]} in file {xml_filepath}"
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
        raise DateException(f"Failed to get a date for {xml_filepath}")

    data["date_filed"] = main_date

    panel_date = (
        date_argued
        or date_reargued
        or date_reargument_denied
        or date_filed
        or unknown_date
    )

    data["panel_date"] = panel_date if panel_date else None

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
    data["panel"] = (
        extract_judge_last_name("".join(data.get("panel", []))) or []
    )

    return data


def update_matching_opinions(
    matches: dict, cl_cleaned_opinions: list, columbia_opinions: list
) -> None:
    """Store matching opinion content in html_columbia
    :param matches: dict with matching position from cl and columbia opinions
    :param cl_cleaned_opinions: list of cl opinions
    :param columbia_opinions: list of columbia opinions
    :return: None
    """
    for columbia_pos, cl_pos in matches.items():
        file_opinion = columbia_opinions[columbia_pos]  # type: dict
        file_byline = file_opinion.get("byline")
        cl_opinion = cl_cleaned_opinions[cl_pos]
        opinion_id_to_update = cl_opinion.get("id")

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
                if (
                    find_just_name(op.author_str).lower()
                    != find_just_name(author_str).lower()
                ):
                    # last resort, use distance between words to solve typos
                    s = SequenceMatcher(
                        None,
                        find_just_name(op.author_str).lower(),
                        find_just_name(author_str).lower(),
                    )
                    if s.ratio() >= 0.6:
                        # columbia names are better
                        op.author_str = author_str
                    else:
                        raise AuthorException(f"Authors don't match")
                elif any(s.isupper() for s in op.author_str.split(",")):
                    # Some names are uppercase, update with processed names
                    op.author_str = author_str

        converted_text = convert_columbia_html(
            file_opinion["opinion"], columbia_pos
        )
        op.html_columbia = str(converted_text)
        op.save()


def map_and_merge_opinions(
    cluster_id: int,
    cl_cleaned_opinions: list[dict],
    columbia_opinions: list[dict],
) -> None:
    """Map and merge opinion data
    :param cluster_id: Cluster id
    :param cl_cleaned_opinions: list of cl opinions
    :param columbia_opinions: list of columbia opinions from file
    """

    if len(columbia_opinions) == len(cl_cleaned_opinions):
        # We need that both list to be cleaned, so we can have a more accurate match
        matches = match_text_lists(
            [
                clean_opinion_content(op["opinion"], harvard_content=False)
                for op in columbia_opinions
            ],
            [op.get("opinion") for op in cl_cleaned_opinions],
        )
        if len(matches) == len(columbia_opinions):
            update_matching_opinions(
                matches, cl_cleaned_opinions, columbia_opinions
            )
        else:
            raise OpinionMatchingException("Failed to match opinions")

    elif (
        len(columbia_opinions) > len(cl_cleaned_opinions)
        and len(cl_cleaned_opinions) == 1
    ):
        for op in columbia_opinions:
            opinion_type = op.get("type")
            file = op.get("file")
            if not opinion_type:
                raise OpinionTypeException(
                    f"Opinion type unknown: {op.get('type')} found in: {file}"
                )
            author = op.get("byline")

            converted_text = convert_columbia_html(op["opinion"], op["order"])

            # TODO add order field if that change gets merged first
            Opinion.objects.create(
                html_columbia=converted_text,
                cluster_id=cluster_id,
                type=opinion_type,
                author_str=titlecase(find_just_name(author.strip(":")))
                if author
                else "",
            )

            logger.info(f"Opinion created for cluster: {cluster_id}")

    else:
        # Skip creating new opinion cluster due to differences between data
        # NOTE: this may happen because some opinions were incorrectly combined when
        # imported with the old columbia importer
        logger.info(
            msg=f"Skip merging mismatched opinions on cluster: {cluster_id}"
        )


def fetch_columbia_metadata(columbia_data: dict) -> dict[str, Any]:
    """Extract only the desired fields
    :param columbia_data: dict with columbia data
    :return: reduced dict
    """
    data = {}

    # List of fields that don't require any additional process
    simple_fields = ["syllabus", "attorneys", "posture"]

    # Convert list of lists to list and titlecase names
    judge_list = list(
        itertools.chain.from_iterable(columbia_data.get("judges", []))
    )
    judge_list = list(map(titlecase, judge_list))
    data["judges"] = ", ".join(sorted(list(set(judge_list))))

    for k, v in columbia_data.items():
        if k in simple_fields:
            data[k] = v if v else ""
    return data


def combine_non_overlapping_data(
    cluster: OpinionCluster, columbia_data: dict
) -> tuple[dict[str, tuple], dict[str, Any]]:
    """Combine non overlapping data and return dictionary of data for merging
    :param cluster: Cluster to merge
    :param columbia_data: The columbia data as json
    :return: Optional dictionary of data to continue to merge
    """
    all_data = fetch_columbia_metadata(columbia_data)
    changed_values_dictionary: dict[str, tuple] = {}
    new_values: dict[str, Any] = {}
    for key, value in all_data.items():
        cl_value = getattr(cluster, key)
        if not cl_value and value:
            # Value is empty in cl for key, we can add it directly to the object
            new_values[key] = value
        else:
            if value != cl_value and value:
                # We have different values and value from file exists, update dict
                # Tuple format: (new value, old value)
                changed_values_dictionary[key] = (value, cl_value)

    return changed_values_dictionary, new_values


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
    cluster: OpinionCluster, columbia_data: dict[str, Any]
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
    overlapping_data: Optional[tuple[str, str]],
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
    field_name: str, overlapping_data: tuple[str, str]
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


def merge_judges(
    overlapping_data: Optional[tuple[str, str]],
) -> dict[str, Any]:
    """Merge overlapping judge values
    :param overlapping_data: data to compare from columbia and courtlistener
    :return: None
    """

    if not overlapping_data:
        return {}

    columbia_data, cl_data = overlapping_data
    # We check if any word in the string is uppercase
    cl_data_upper = (
        True if [s for s in cl_data.split(",") if s.isupper()] else False
    )

    # Get last names keeping case and cleaning the string (We could have
    # the judge names in capital letters)
    cl_clean = set(find_all_judges(cl_data))
    # Lowercase courtlistener judge names for set operations
    temp_cl_clean = set([c.lower() for c in cl_clean])
    # Get last names in lowercase and cleaned
    columbia_clean = set(find_all_judges(columbia_data))
    # Lowercase columbia judge names for set operations
    temp_columbia_clean = set([h.lower() for h in columbia_clean])
    # Prepare judges string
    judges = titlecase(", ".join(find_all_judges(columbia_data)))

    if (
        temp_columbia_clean.issuperset(temp_cl_clean) or cl_data_upper
    ) and columbia_clean != cl_clean:
        return {"judges": judges}
    elif not temp_columbia_clean.intersection(temp_cl_clean):
        raise JudgeException("Judges are completely different.")

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

    long_fields = ["syllabus", "posture", "judges"]

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
        elif field_name == "judges":
            data_to_update.update(
                merge_judges(changed_values_dictionary.get(field_name, ""))
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
    if new_docket_source in VALID_UPDATED_DOCKET_SOURCES:
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
    if new_cluster_source in VALID_MERGED_SOURCES:
        cluster.source = new_cluster_source
        cluster.save()
    else:
        raise ClusterSourceException(
            f"Unexpected cluster source: {new_cluster_source}"
        )


def update_panel(
    cluster: OpinionCluster,
    panel_list: list[str],
    panel_date: Optional[date] = None,
) -> None:
    """Update cluster's panel
    :param cluster: the cluster object
    :param panel_list: list with people names
    :param panel_date: date used to find people
    """

    panel_list = [titlecase(p) for p in panel_list]

    panel = async_to_sync(lookup_judges_by_last_name_list)(
        panel_list, cluster.docket.court.id, panel_date
    )

    if panel:
        cluster.panel.add(*Person.objects.filter(id__in=[p.id for p in panel]))


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


def process_cluster(
    cluster_id: int,
    xml_dir: str,
    filepath: str = "",
    csv_file: bool = False,
) -> None:
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

    if (
        cluster.docket.source in VALID_UPDATED_DOCKET_SOURCES
        or cluster.source in VALID_MERGED_SOURCES
    ):
        # Early abort if docket or cluster already merged
        return

    xml_path, cl_cleaned_opinions = get_cl_opinion_content(cluster.id)

    if not xml_path and not csv_file:
        # When we pass a cluster id directly to the command and the cluster opinions
        # don't have a xml file
        logger.info(
            f"Cluster ID: {cluster_id} doesn't have a local_path field value."
        )
        return

    if filepath:
        # Filepath from csv file
        new_xml_filepath = fix_filepath(filepath, xml_dir)
    else:
        # Filepath from opinion local_path field
        new_xml_filepath = fix_filepath(xml_path, xml_dir)  # type: ignore

    try:
        logger.info(msg=f"Merging {cluster_id} at {new_xml_filepath}")
        columbia_data = read_xml_file(new_xml_filepath)
    except FileNotFoundError:
        logger.warning(
            f"File doesn't exist: {new_xml_filepath} to merge with cluster: {cluster_id}"
        )
        return
    except UnicodeDecodeError:
        logger.warning(
            f"Cannot decode file: {new_xml_filepath} to merge with cluster: {cluster_id}"
        )
        return
    except DateException:
        logger.warning(
            msg=f"Date exception found in {new_xml_filepath} related to cluster id: {cluster_id}"
        )
        return

    try:
        with transaction.atomic():
            map_and_merge_opinions(
                cluster_id, cl_cleaned_opinions, columbia_data["opinions"]
            )
            # Non overlapping data and new values for cluster fields
            (
                changed_values_dictionary,
                new_values,
            ) = combine_non_overlapping_data(cluster, columbia_data)
            # docket number
            if columbia_data["docket"]:
                merge_docket_numbers(cluster, columbia_data["docket"])
            # case names
            case_names_to_update = merge_case_names(cluster, columbia_data)
            # date filed
            date_filed_to_update = merge_date_filed(cluster, columbia_data)
            # overlapping data
            overlapping_data_to_update = merge_overlapping_data(
                cluster, changed_values_dictionary
            )
            # panel
            if columbia_data["panel"]:
                update_panel(
                    cluster,
                    columbia_data["panel"],
                    columbia_data["panel_date"],
                )

            # Merge results into a single dict
            data_to_update = (
                new_values
                | case_names_to_update
                | date_filed_to_update
                | overlapping_data_to_update
            )

            if data_to_update:
                # all data is updated at once
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


def process_csv_file(
    csv_path: str, mounted_xml_dir: str, skip_until_id: Optional[int]
) -> None:
    """Process xml files from a list of cluster ids in csv file
    :param csv_path: Absolute path to csv file
    :param mounted_xml_dir: Path to mounted dir
    """
    logger.info(f"Loading csv file at {csv_path}")

    with open(csv_path, mode="r", encoding="utf-8") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        start = False
        for row in csv_reader:
            cluster_id = row.get("cluster_id")
            filepath = row.get("filepath")
            if cluster_id and filepath:
                if skip_until_id and not start:
                    if int(cluster_id) != skip_until_id:
                        continue
                    else:
                        start = True

                process_cluster(cluster_id=cluster_id, xml_dir=mounted_xml_dir, filepath=filepath, csv_file=True)  # type: ignore


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
            default="/opt/courtlistener/columbia_import.csv",
            help="Csv file with cluster ids to merge.",
            required=False,
        )

        parser.add_argument(
            "--xml-dir",
            default="/tmp/columbia",
            required=False,
            help="The absolute path to the directory with columbia xml files",
        )

        parser.add_argument(
            "--skip-until-id",
            type=int,
            help="Skip until cluster ID",
            required=False,
        )

    def handle(self, *args, **options) -> None:
        if options["cluster_id"]:
            process_cluster(
                cluster_id=options["cluster_id"], xml_dir=options["xml_dir"]
            )
            sys.exit()

        if options["csv_file"]:
            process_csv_file(
                options["csv_file"],
                mounted_xml_dir=options["xml_dir"],
                skip_until_id=options["skip_until_id"],
            )
