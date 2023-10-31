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
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Optional

from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup, NavigableString, Tag
from django.db import transaction
from django.db.models import Q
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
    DocketSourceException,
    EmptyOpinionException,
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


def clean_opinion_content(content: str, is_harvard: bool) -> str:
    """Strip all non-alphanumeric characters
    :param content: content from opinion
    :param is_harvard: true if content is from harvard
    :return: cleaned content
    """
    soup = BeautifulSoup(content, features="html.parser")

    if is_harvard:
        for op in soup.select("opinion"):
            # Remove any author tag inside opinion
            for extra in op.find_all(["author"]):
                extra.extract()

    prep_text = re.sub(
        r"[^a-zA-Z0-9 ]", "", soup.getText(separator=" ").lower()
    )
    prep_text = re.sub(" +", " ", prep_text)
    return prep_text


def get_cl_opinion_content(cluster_id: int) -> list[dict[Any, Any]]:
    """Get the opinions content for a cluster object
    :param cluster_id: Cluster ID for a set of opinions
    :return: list with opinion content from cl
    """
    cl_cleaned_opinions = []
    opinions_from_cluster = Opinion.objects.filter(cluster_id=cluster_id)
    is_harvard = False

    for i, op in enumerate(opinions_from_cluster):
        content = None
        if len(op.xml_harvard) > 1:
            content = op.xml_harvard
            is_harvard = True
        elif len(op.html_with_citations) > 1:
            content = op.html_with_citations
        elif len(op.html_columbia) > 1:
            content = op.html_columbia
        elif len(op.html_lawbox) > 1:
            content = op.html_lawbox
        elif len(op.plain_text) > 1:
            content = op.plain_text
        elif len(op.html) > 1:
            content = op.html

        if not content:
            raise EmptyOpinionException("No content in opinion")

        prep_text = clean_opinion_content(content, is_harvard=is_harvard)
        cl_cleaned_opinions.append(
            {
                "id": op.id,
                "byline": op.author_str,
                "type": op.type,
                "opinion": prep_text,
            }
        )

    return cl_cleaned_opinions


def is_opinion_published(soup: BeautifulSoup) -> bool:
    """Check if opinion is unpublished or published
    :param soup: The XML object
    :return: Published or Unpublished
    """
    # TODO check this function
    opinion_tag = soup.find("opinion")

    if opinion_tag:
        if opinion_tag.get("unpublished") == "true":
            return False
        if opinion_tag.find("unpublished"):
            return False
    return True


def read_xml_to_soup(filepath: str):
    """This function fixes the bad tags in columbia xml files
    :param filepath: path to xml file
    :return: string with content
    """
    with open(filepath, "r", encoding="utf-8") as f:
        file_content = f.read()
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
    return BeautifulSoup(file_content, "lxml")


def add_floating_opinion(opinions: list, floating_content: list) -> list:
    """We have found floating opinions in bs object, we keep the opinion content as a
    new opinion
    :param opinions: a list with opinions found
    :param floating_content: content that is not in known non-opinion tags
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
                "byline": "",
                "type": op_type,
            }
        )
    return opinions


def extract_opinions_bs(outer_opinion: BeautifulSoup) -> list[Optional[dict]]:
    """We extract all possible opinions from bs content, with and without author,
    and we create new opinions if floating content exists
    :param outer_opinion:
    :return:
    """
    opinions: list = []
    floating_content = []

    # We iterate all content to look for all possible opinions
    for i, content in enumerate(outer_opinion):  # type: int, Tag
        if type(content) == NavigableString:
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
                    # We have found an opinion, but there is floating content, we
                    # create a dict with the opinion using the floating content with
                    # default type = "opinion"
                    opinions = add_floating_opinion(opinions, floating_content)
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
                            "byline": opinion_author,
                            "type": content.name.replace("_text", ""),
                        }
                    )

            else:
                if content.name not in SIMPLE_TAGS + ["syllabus"]:
                    # We store content that is not inside _text tag and is not in
                    # one of the known non-opinion tags
                    floating_content.append(str(content))

    # Combine the new content into another opinion. great.
    if floating_content:
        # If we end to go through all the found opinions and if we still have
        # floating content out there, we create a new opinion with the last type
        # of opinion
        opinions = add_floating_opinion(opinions, floating_content)
    return opinions


def merge_opinions(opinions, content) -> list:
    """Merge last and previous opinion if are the same type or create a new opinion if merge is not possible
    :param opinions: list of opinions that is being updated constantly
    :param content: list of opinions without an author
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
        new_opinion = {
            "byline": None,
            "type": content[0].get("type"),
            "opinion": "\n".join(
                [f.get("opinion") for f in content if f.get("opinion")]
            ),
        }
        opinions.append(new_opinion)

    return opinions


def prepare_opinions_found(extracted_opinions: list) -> list:
    """We read the opinions found, and we combine or create floating opinions
    :param extracted_opinions: list of opinions obtained from xml file
    :return:
    """

    opinions: list = []
    authorless_content = []

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
                opinions = merge_opinions(
                    opinions, alternative_authorless_content
                )

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
            }

            opinions.append(new_opinion)
            authorless_content = []

        if len(extracted_opinions) == i and authorless_content:
            # If is the last opinion, and we still have opinions without
            # byline, create an opinion without an author and the contents
            # that couldn't be merged
            opinions = merge_opinions(opinions, authorless_content)

    return opinions


def find_judge_and_type(columbia_data: dict):
    """
    # only first opinion with "opinion" type is a lead opinion, the next opinion with
    # "opinion" type is an addendum
    :param columbia_data:
    :return:
    """

    columbia_data["judges"] = []
    lead = False
    for op in columbia_data.get("opinions", []):
        op_type = op.get("type")

        op_byline = op.get("byline")
        if op_byline:
            judge_name = extract_judge_last_name(op_byline)
            if judge_name not in columbia_data["judges"]:
                columbia_data["judges"].append(judge_name)

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


def fix_reporter_caption(soup):
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


def fix_simple_tags(soup, columbia_data):
    """
    :param soup:
    :param columbia_data:
    """
    for tag in SIMPLE_TAGS:
        found_tags = soup.findAll(tag)
        for found_tag in found_tags:
            # found_tag.find("page_number").decompose()
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
        columbia_data[tag] = [
            found_tag.get_text(separator=" ").strip()
            for found_tag in found_tags
        ]

        if tag in ["attorneys", "posture"]:
            # Replace multiple line breaks in this specific fields
            columbia_data[tag] = [
                re.sub("\n+", " ", c) for c in columbia_data.get(tag, [])
            ]

        if tag in ["reporter_caption"]:
            # Remove the last comma from the case name
            columbia_data[tag] = [
                c.rstrip(",") for c in columbia_data.get(tag, [])
            ]

        # Remove repeated spaces
        columbia_data[tag] = [
            re.sub(" +", " ", c) for c in columbia_data.get(tag, [])
        ]

        if tag == "citation":
            # Remove duplicated citations,
            columbia_data[tag] = list(set(columbia_data[tag]))

    # return data


def extract_dates(columbia_data: dict):
    """Get dates
    :param columbia_data:
    """
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
                        f"Found unknown date tag {date_info[0]} with date {date_info[1]} in file FILEPATH?"
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
    columbia_data["date_filed"] = main_date

    panel_date = (
        date_argued
        or date_reargued
        or date_reargument_denied
        or date_filed
        or unknown_date
    )

    columbia_data["panel_date"] = panel_date if panel_date else None
    # return data


def format_additional_fields(data, soup):
    """Prepare data and rename key names to match model field names
    :param data: dict with data extracted from xml
    :param soup: bs object
    """
    data["syllabus"] = "\n".join(
        [s.decode_contents() for s in soup.findAll("syllabus")]
    )
    data["docket"] = "".join(data.get("docket", [])) or None
    data["attorneys"] = "\n".join(data.get("attorneys", [])) or None
    data["posture"] = "".join(data.get("posture", [])) or None
    data["case_name_full"] = (
        format_case_name("".join(data.pop("caption", []))) or ""
    )
    data["case_name"] = (
        format_case_name("".join(data.pop("reporter_caption", []))) or ""
    )
    data["panel"] = (
        extract_judge_last_name("".join(data.get("panel", []))) or []
    )


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
                clean_opinion_content(op["opinion"], is_harvard=False)
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


def process_cluster(
    cluster_id: int,
    filepath: str,
) -> None:
    """Merge specified cluster id
    :param cluster_id: Cluster object id to merge
    :param filepath: specified path to xml file
    """
    columbia_data: dict = {}

    cluster = (
        OpinionCluster.objects.filter(id=cluster_id)
        .exclude(
            Q(source__in=VALID_MERGED_SOURCES)
            | Q(docket__source__in=VALID_UPDATED_DOCKET_SOURCES)
        )
        .first()
    )
    if not cluster:
        return

    logger.info(msg=f"Merging {cluster_id} at {filepath}")
    try:
        soup = read_xml_to_soup(filepath)
    except UnicodeDecodeError:
        logger.warning(
            f"UnicodeDecodeError: {filepath}, Cluster: {cluster_id}"
        )
        return

    columbia_data["published"] = is_opinion_published(soup)

    outer_opinion = soup.find("opinion")
    if not outer_opinion:
        # opinion wraps around all xml content
        logger.warning("Ill formed xml columbia")

    extracted_opinions = extract_opinions_bs(outer_opinion)
    columbia_data["opinions"] = prepare_opinions_found(extracted_opinions)
    columbia_data["file"] = filepath
    find_judge_and_type(columbia_data)
    fix_simple_tags(soup, columbia_data)
    extract_dates(columbia_data)

    if not columbia_data["date_filed"]:
        logger.warning(msg=f"No Date found {filepath}, Cluster: {cluster_id}")
        return

    format_additional_fields(columbia_data, soup)

    try:
        cl_cleaned_opinions = get_cl_opinion_content(cluster.id)
    except EmptyOpinionException:
        logger.warning(msg=f"No content in opinion from cluster: {cluster_id}")
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


def merge_columbia_into_cl(options) -> None:
    """Merge Columbia Data into CL
    :param options: Absolute path to csv file
    """
    csv_filepath, xml_dir = options["csv_file"], options["xml_dir"]
    skip_until, limit = options["skip_until"], options["limit"]
    logger.info(f"Loading csv file at {csv_filepath}")

    total_processed = 0
    start = False if skip_until else True
    with open(csv_filepath, mode="r", encoding="utf-8") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            cluster_id = row.get("cluster_id")
            filepath = row.get("filepath")
            if not start and skip_until == cluster_id:
                start = True
            if not start:
                continue

            # TODO
            # xml_path = f"{xml_dir}/documents/{filepath}"
            xml_path = filepath
            if not os.path.exists(xml_path):
                logger.warning(
                    f"No file at: {xml_path}, Cluster: {cluster_id}"
                )
                continue

            process_cluster(
                cluster_id=cluster_id,
                filepath=xml_path,
            )

            total_processed += 1
            if limit and total_processed >= limit:
                logger.info(f"Finished {limit} imports")
                return


class Command(VerboseCommand):
    help = "Merge columbia opinions"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--skip-until",
            type=int,
            help="An individual cluster ID to merge",
            required=False,
        )

        parser.add_argument(
            "--csv-file",
            default="/opt/courtlistener/_columbia/columbia_import.csv",
            help="Csv file with cluster ids to merge.",
            required=False,
        )

        parser.add_argument(
            "--limit",
            default=1,
            type=int,
            help="Limit number of files to merge",
            required=False,
        )

        parser.add_argument(
            "--xml-dir",
            default="/opt/courtlistener/_columbia",
            required=False,
            help="The absolute path to the directory with columbia xml files",
        )

    def handle(self, *args, **options) -> None:
        merge_columbia_into_cl(options)
