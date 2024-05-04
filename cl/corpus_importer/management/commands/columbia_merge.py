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

You can revert the changes if you pass --debug option to command
manage.py columbia_merge --debug --csv-file /opt/courtlistener/cl/assets/media/test1.csv


"""

import os.path
import re
from difflib import SequenceMatcher
from typing import Any, Optional

import pandas as pd
from bs4 import BeautifulSoup
from django.db import transaction
from django.db.models import Q
from juriscraper.lib.string_utils import titlecase

from cl.corpus_importer.import_columbia.columbia_utils import (
    convert_columbia_html,
    extract_columbia_opinions,
    fetch_simple_tags,
    find_dates_in_xml,
    find_judges,
    format_case_name,
    is_opinion_published,
    map_opinion_types,
    process_extracted_opinions,
    read_xml_to_soup,
)
from cl.corpus_importer.utils import (
    AuthorException,
    CitationException,
    JudgeException,
    OpinionMatchingException,
    OpinionTypeException,
    add_citations_to_cluster,
    clean_docket_number,
    match_opinion_lists,
    merge_case_names,
    merge_docket_numbers,
    merge_judges,
    merge_long_fields,
    merge_strings,
    update_cluster_panel,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.lookup_utils import extract_judge_last_name, find_just_name
from cl.search.models import SOURCES, Docket, Opinion, OpinionCluster

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

    # Replace line breaks with spaces and get rid of double spaces
    prep_text = re.sub(
        " +", " ", " ".join(soup.getText(separator=" ").split("\n"))
    ).strip()

    # Remove non-alphanumeric and non-whitespace characters from lowercased text
    prep_text = re.sub(r"[^a-zA-Z0-9 ]", "", prep_text.lower())

    return prep_text


def get_cl_opinion_content(
    cluster_id: int, columbia_single_opinion: bool = False
) -> list[dict[Any, Any]]:
    """Get the opinions content for a cluster object

    :param cluster_id: Cluster ID for a set of opinions
    :param columbia_single_opinion: True if xml file only has one opinion else False
    :return: list with opinion content from cl
    """
    cl_cleaned_opinions = []

    # Get all opinions from cluster
    opinions_from_cluster = Opinion.objects.filter(cluster_id=cluster_id)

    if not columbia_single_opinion:
        # File has multiple opinions, then we can exclude combined opinions
        opinions_from_cluster = opinions_from_cluster.exclude(
            type="010combined"
        )

    is_harvard = False

    for i, op in enumerate(opinions_from_cluster):
        content = ""
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
    matches: dict,
    cl_cleaned_opinions: list,
    columbia_opinions: list,
    filepath: str,
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
                        raise AuthorException("Authors don't match")
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
    filepath: str,
) -> None:
    """Map and merge opinion data

    :param cluster_id: Cluster id
    :param columbia_opinions: list of columbia opinions from file
    :param filepath: xml file from which the opinion was extracted
    :return: None
    """

    # Check if columbia source only has one opinion
    columbia_single_opinion = True if len(columbia_opinions) == 1 else False

    # We exclude combined opinions only if we have more than one opinion in the xml
    cl_cleaned_opinions = get_cl_opinion_content(
        cluster_id, columbia_single_opinion
    )

    if len(columbia_opinions) == len(cl_cleaned_opinions):
        # We need that both list to be cleaned, so we can have a more
        # accurate match
        matches = match_opinion_lists(
            [
                clean_opinion_content(op["opinion"], is_harvard=False)
                for op in columbia_opinions
            ],
            [op.get("opinion") for op in cl_cleaned_opinions],
        )
        if len(matches) == len(columbia_opinions):
            # We were able to match opinions, add opinions to html_columbia field
            update_matching_opinions(
                matches, cl_cleaned_opinions, columbia_opinions, filepath
            )
        else:
            raise OpinionMatchingException("Failed to match opinions")

    elif (len(columbia_opinions) > len(cl_cleaned_opinions)) and len(
        cl_cleaned_opinions
    ) == 0:
        # We have more opinions in file than in CL and if cl_cleaned_opinions == 0 it
        # means that we probably excluded the combined opinion, we create each
        # opinion from file
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
                per_curiam=op["per_curiam"],
                cluster_id=cluster_id,
                type=opinion_type,
                local_path=filepath,
                author_str=(
                    titlecase(find_just_name(author.strip(":")))
                    if author
                    else ""
                ),
            )

            logger.info(f"Opinion created for cluster: {cluster_id}")

    else:
        # Skip creating new opinions due to differences between data,
        # this may happen because some opinions were incorrectly combined
        # when imported with the old columbia importer, or we have combined
        # opinions
        raise OpinionMatchingException(
            f"Skip merging mismatched opinions on cluster: {cluster_id}"
        )


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


def merge_field(
    cluster: OpinionCluster,
    file_value: Optional[str],
    field_name: str,
    skip_judge_merger: bool = False,
) -> dict:
    """Try to merge the cluster data and file field data

    :param cluster: the cluster object
    :param file_value: the value from file field
    :param field_name: the field name to work with
    :param skip_judge_merger: skip judge merger
    :return: dict
    """
    cl_value = getattr(cluster, field_name)
    if not file_value:
        return {}
    if file_value and not cl_value:
        return {field_name: file_value}
    if file_value and cl_value:
        if field_name in ["syllabus", "posture"]:
            return merge_long_fields(
                field_name, (file_value, cl_value), cluster.id
            )
        elif field_name == "attorneys":
            return merge_strings(field_name, (file_value, cl_value))
        elif field_name == "judges":
            return merge_judges(
                (file_value, cl_value),
                cluster.id,
                is_columbia=True,
                skip_judge_merger=skip_judge_merger,
            )
        else:
            logger.info(f"Field not considered in the process: {field_name}")

    return {}


def merge_docket_data(docket_data: dict, cluster: OpinionCluster) -> None:
    """Update docket with new or better data

    For dates, we only care if we have a date in the file but not in the
    Docket object

    :param docket_data: dict with data from file
    :param cluster: OpinionCluster object
    :return: None
    """

    data_to_update = {}

    if docket_data["docket_number"]:
        merge_docket_numbers(cluster, docket_data["docket_number"])
        cluster.docket.refresh_from_db()
    if (
        docket_data["date_cert_granted"]
        and not cluster.docket.date_cert_granted
    ):
        data_to_update["date_cert_granted"] = docket_data["date_cert_granted"]

    if docket_data["date_cert_denied"] and not cluster.docket.date_cert_denied:
        data_to_update["date_cert_denied"] = docket_data["date_cert_denied"]

    if docket_data["date_argued"] and not cluster.docket.date_argued:
        data_to_update["date_argued"] = docket_data["date_argued"]

    if docket_data["date_reargued"] and not cluster.docket.date_reargued:
        data_to_update["date_reargued"] = docket_data["date_reargued"]

    if (
        docket_data["date_reargument_denied"]
        and not cluster.docket.date_reargument_denied
    ):
        data_to_update["date_reargument_denied"] = docket_data[
            "date_reargument_denied"
        ]

    if data_to_update:
        Docket.objects.filter(id=cluster.docket_id).update(**data_to_update)


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
        OpinionCluster.objects.filter(
            id=cluster_id, docket__source__in=Docket.NON_COLUMBIA_SOURCES()
        )
        .exclude(source__in=VALID_MERGED_SOURCES)
        .first()
    )
    if not cluster:
        logger.info(f"Cluster id: {cluster_id} already merged")
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
    extracted_opinions = extract_columbia_opinions(outer_opinion)
    opinions = process_extracted_opinions(extracted_opinions)
    map_opinion_types(opinions)

    panel_tags = "".join(fetch_simple_tags(soup, "panel"))
    reporter_captions = "".join(fetch_simple_tags(soup, "reporter_caption"))
    captions = "".join(fetch_simple_tags(soup, "caption"))
    syllabus = "\n".join(
        [s.decode_contents() for s in soup.findAll("syllabus")]
    )
    docket_number = "".join(fetch_simple_tags(soup, "docket"))
    attorneys = "\n".join(fetch_simple_tags(soup, "attorneys"))
    posture = "".join(fetch_simple_tags(soup, "posture"))

    columbia_data: dict = {
        "published": is_opinion_published(soup),
        "file": filepath,
        "attorneys": attorneys,
        "citations": fetch_simple_tags(soup, "citation"),
        "docket_number": (
            clean_docket_number(docket_number) if docket_number else None
        ),
        "panel": extract_judge_last_name(panel_tags),
        "posture": posture,
        "case_name": format_case_name(reporter_captions),
        "case_name_full": format_case_name(captions),
        "judges": find_judges(opinions),
        "syllabus": syllabus,
        "opinions": opinions,
    }

    # Add date data into columbia dict
    columbia_data.update(find_dates_in_xml(soup))

    # Extract all data related to docket
    docket_data = {
        k: v
        for k, v in columbia_data.items()
        if k
        in [
            "docket_number",
            "date_cert_granted",
            "date_cert_denied",
            "date_argued",
            "date_reargued",
            "date_reargument_denied",
        ]
    }

    try:
        with transaction.atomic():
            map_and_merge_opinions(
                cluster_id, columbia_data["opinions"], filepath
            )

            merged_data = {}
            for field in ["syllabus", "attorneys", "posture", "judges"]:
                columbia_value = columbia_data.get(field)
                if data := merge_field(
                    cluster,
                    columbia_value,
                    field,
                    skip_judge_merger=skip_judge_merger,
                ):
                    merged_data.update(data)

            case_names_to_update = merge_case_names(
                cluster,
                columbia_data,
                case_name_key="case_name",
                case_name_full_key="case_name_full",
            )
            date_filed_to_update = merge_date_filed(cluster, columbia_data)

            if columbia_data["panel"]:
                update_cluster_panel(
                    cluster,
                    columbia_data["panel"],
                    columbia_data["panel_date"],
                )

            # Merge results into a single dict
            data_to_update = (
                merged_data | case_names_to_update | date_filed_to_update
            )

            if data_to_update:
                # all data is updated at once
                OpinionCluster.objects.filter(id=cluster_id).update(
                    **data_to_update
                )

            add_citations_to_cluster(columbia_data["citations"], cluster_id)

            merge_docket_data(docket_data, cluster)

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
    except CitationException:
        logger.warning(
            msg=f"Invalid citation found in {filepath} while merging cluster id: {cluster_id}"
        )


def merge_columbia_into_cl(options) -> None:
    """Merge columbia data into CL

    :param options: options passed from management command
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
            default="/tmp/columbia",
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
