"""
Command to merge opinions with columbia xml file

Merge using a csv file with cluster id and xml file path pointing to a file path
manage.py columbia_merge --csv-file /opt/courtlistener/cl/assets/media/test1.csv

The absolute path to the xml file is a combination of xml-dir param and xml filepath,
e.g. "/opt/courtlistener/_columbia" +
"michigan/supreme_court_opinions/documents/d5a484f1bad20ba0.xml"

Csv example:
cluster_id,filepath
825802,michigan/supreme_court_opinions/documents/d5a484f1bad20ba0.xml

"""
import os.path
import re
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Optional

import pandas as pd
from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from django.db import transaction
from django.db.models import Q
from juriscraper.lib.string_utils import titlecase

from cl.corpus_importer.import_columbia.columbia_utils import (
    convert_columbia_html,
    extract_opinions,
    fetch_simple_tags,
    find_judges,
    format_case_name,
    is_opinion_published,
    map_opinion_types,
    parse_and_extract_dates,
    process_extracted_opinions,
    read_xml_to_soup,
)
from cl.corpus_importer.utils import (
    AuthorException,
    JudgeException,
    OpinionMatchingException,
    OpinionTypeException,
    add_citations_to_cluster,
    match_opinion_lists,
    merge_case_names,
    merge_docket_numbers,
    merge_overlapping_data,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.lookup_utils import (
    extract_judge_last_name,
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


def update_matching_opinions(
    matches: dict, cl_cleaned_opinions: list, columbia_opinions: list
) -> None:
    """Store matching opinion content in html_columbia field from Opinion object

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
    columbia_opinions: list[dict],
) -> None:
    """Map and merge opinion data

    :param cluster_id: Cluster id
    :param columbia_opinions: list of columbia opinions from file
    :return: None
    """

    cl_cleaned_opinions = get_cl_opinion_content(cluster_id)

    if len(columbia_opinions) == len(cl_cleaned_opinions):
        # We need that both list to be cleaned, so we can have a more accurate match
        matches = match_opinion_lists(
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

    elif len(columbia_opinions) > len(cl_cleaned_opinions) == 1:
        for op in columbia_opinions:
            opinion_type = op.get("type")
            file = op.get("file")
            if not opinion_type:
                raise OpinionTypeException(
                    f"Opinion type unknown: {op.get('type')} found in: {file}"
                )
            author = op.get("byline")

            converted_text = convert_columbia_html(op["opinion"], op["order"])

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
        # Skip creating new opinions due to differences between data, this may happen
        # because some opinions were incorrectly combined when imported with the old
        # columbia importer, or we have combined opinions
        logger.info(
            msg=f"Skip merging mismatched opinions on cluster: {cluster_id}"
        )


def combine_non_overlapping_data(
    cluster: OpinionCluster, columbia_data: dict
) -> tuple[dict[str, tuple], dict[str, Any]]:
    """Combine non overlapping data and return dictionary of data for merging

    :param cluster: Cluster to merge
    :param columbia_data: The columbia data as json
    :return: Optional dictionary of data to continue to merge
    """

    # this function only applies to a few fields because some fields are processed
    # into independent functions
    fields_to_get = ["syllabus", "attorneys", "posture", "judges"]
    fields_data = {
        k: v for k, v in columbia_data.items() if k in fields_to_get
    }
    changed_values_dictionary: dict[str, tuple] = {}
    new_values: dict[str, Any] = {}
    for key, value in fields_data.items():
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


def merge_date_filed(
    cluster: OpinionCluster, columbia_data: dict
) -> dict[str, Any]:
    """Merge date filed

    :param cluster: The cluster of the merging item
    :param columbia_data: json data from columbia
    :return: empty dict or dict with new value for field
    """

    columbia_date_filed = columbia_data.get("date_filed")
    cluster_date_filed = cluster.date_filed

    if columbia_date_filed:
        if cluster.docket.source == Docket.SCRAPER:
            # Give preference to columbia data
            if columbia_date_filed != cluster_date_filed:
                return {"date_filed": columbia_date_filed}

    return {}


def update_docket_source(cluster: OpinionCluster) -> None:
    """Update docket source and complete

    :param cluster: the cluster object
    :return: None
    """
    docket = cluster.docket
    docket.source = Docket.COLUMBIA + docket.source
    docket.save()


def update_cluster_source(cluster: OpinionCluster) -> None:
    """Update cluster source

    :param cluster: cluster object
    :return: None
    """
    cluster.source = SOURCES.COLUMBIA_ARCHIVE + cluster.source
    cluster.save()


def update_cluster_panel(
    cluster: OpinionCluster,
    panel_list: list[str],
    panel_date: Optional[date] = None,
) -> None:
    """Update cluster's panel

    This is done independently since it is a m2m relationship, we collect the
    corrected names, find the Person ids and then add them to the relation

    :param cluster: the cluster object
    :param panel_list: list with people names
    :param panel_date: date used to find people
    :return: None
    """

    panel_list = [titlecase(p) for p in panel_list]
    panel = async_to_sync(lookup_judges_by_last_name_list)(
        panel_list, cluster.docket.court.id, panel_date, True
    )
    if panel:
        cluster.panel.add(*Person.objects.filter(id__in=[p.id for p in panel]))


def process_cluster(
    cluster_id: int,
    filepath: str,
    skip_judge_merger: bool = False,
) -> None:
    """Merge specified cluster id

    :param cluster_id: Cluster object id to merge
    :param filepath: specified path to xml file
    :param skip_judge_merger: skip judge merger
    :return: None
    """

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

    outer_opinion = soup.find("opinion")
    extracted_opinions = extract_opinions(outer_opinion)
    opinions = process_extracted_opinions(extracted_opinions)
    map_opinion_types(opinions)

    columbia_data: dict = {
        "published": is_opinion_published(soup),
        "file": filepath,
        "attorneys": "\n".join(fetch_simple_tags(soup, "attorneys")) or "",
        "citations": fetch_simple_tags(soup, "citation"),
        "date": fetch_simple_tags(soup, "date"),
        "docket": "".join(fetch_simple_tags(soup, "docket")) or None,
        "hearing_date": fetch_simple_tags(soup, "hearing_date"),
        "panel": extract_judge_last_name(
            "".join(fetch_simple_tags(soup, "panel"))
        )
        or [],
        "posture": "".join(fetch_simple_tags(soup, "posture")) or "",
        "case_name": format_case_name(
            "".join(fetch_simple_tags(soup, "reporter_caption"))
        )
        or "",
        "case_name_full": format_case_name(
            "".join(fetch_simple_tags(soup, "caption"))
        )
        or "",
        "judges": find_judges(opinions),
        "syllabus": "\n".join(
            [s.decode_contents() for s in soup.findAll("syllabus")]
        )
        or "",
        "opinions": opinions,
    }

    parse_and_extract_dates(columbia_data)

    try:
        with transaction.atomic():
            map_and_merge_opinions(cluster_id, columbia_data["opinions"])
            (
                changed_values_dictionary,
                new_values,
            ) = combine_non_overlapping_data(cluster, columbia_data)
            if columbia_data["docket"]:
                merge_docket_numbers(cluster, columbia_data["docket"])
            case_names_to_update = merge_case_names(
                cluster,
                columbia_data,
                case_name_key="case_name",
                case_name_full_key="case_name_full",
            )
            date_filed_to_update = merge_date_filed(cluster, columbia_data)
            overlapping_data_long_fields = ["syllabus", "posture"]
            overlapping_data_to_update = merge_overlapping_data(
                cluster,
                overlapping_data_long_fields,
                changed_values_dictionary,
                skip_judge_merger,
                is_columbia=True,
            )
            if columbia_data["panel"]:
                update_cluster_panel(
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

            add_citations_to_cluster(columbia_data["citations"], cluster_id)

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
    except JudgeException:
        logger.warning(msg=f"Judge exception for cluster id: {cluster_id}")


def merge_columbia_into_cl(options) -> None:
    """Merge columbia data into CL

    :param options: options passed to management command
    :return: None
    """
    csv_filepath, xml_dir = options["csv_file"], options["xml_dir"]
    skip_until, limit = options["skip_until"], options["limit"]
    skip_judge_merger = options["skip_judge_merger"]
    total_processed = 0
    start = False if skip_until else True

    logger.info(f"Loading csv file at {csv_filepath}")
    data = pd.read_csv(
        csv_filepath, delimiter=",", dtype={"cluster_id": int, "filepath": str}
    )

    for index, item in data.iterrows():
        cluster_id = item["cluster_id"]
        filepath = item["filepath"]

        if not start and skip_until == cluster_id:
            start = True
        if not start:
            continue

        # filepath example: indiana\court_opinions\documents\2713f39c5a8e8684.xml
        xml_path = os.path.join(xml_dir, filepath)
        if not os.path.exists(xml_path):
            logger.warning(f"No file at: {xml_path}, Cluster: {cluster_id}")
            continue

        process_cluster(
            cluster_id=cluster_id,
            filepath=xml_path,
            skip_judge_merger=skip_judge_merger,
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
            default=10000,
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

        parser.add_argument(
            "--skip-judge-merger",
            action="store_true",
            help="Set flag to skip judge merger if the judges do not match",
        )

    def handle(self, *args, **options) -> None:
        merge_columbia_into_cl(options)
