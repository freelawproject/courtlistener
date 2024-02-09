"""
Command to import opinions from columbia xlml file

Import using a csv file with xml file path pointing to mounted directory and filepath
manage.py import_columbia --csv-file /opt/courtlistener/cl/assets/media/testfile.csv

Csv example:
filepath
michigan/supreme_court_opinions/documents/d5a484f1bad20ba0.xml

"""

import os
from datetime import timedelta
from typing import Optional

import pandas as pd
from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import transaction
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from juriscraper.lib.string_utils import CaseNameTweaker, titlecase

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
    add_citations_to_cluster,
    clean_body_content,
    clean_docket_number,
    get_court_id,
    match_based_text,
    update_cluster_panel,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.crypto import sha1_of_file
from cl.people_db.lookup_utils import (
    extract_judge_last_name,
    lookup_judge_by_last_name,
)
from cl.search.models import SOURCES, Court, Docket, Opinion, OpinionCluster

CASE_NAME_TWEAKER = CaseNameTweaker()


def find_duplicates(
    data: dict, valid_citations: list
) -> Optional[OpinionCluster]:
    """Check if there is a duplicate cluster

    :param data: The columbia data
    :param valid_citations: list with valid citations
    :return: cluster match or None
    """

    docket_number = data["docket_number"] or ""
    case_name = data["case_name"] or ""
    case_name_short = data["case_name_short"] or ""

    for citation in valid_citations:
        xml_opinions_content = []
        for op in data["opinions"]:
            xml_opinions_content.append(op["opinion"])

        all_opinions_content = " ".join(xml_opinions_content)
        all_opinions_soup = BeautifulSoup(
            all_opinions_content, features="html.parser"
        )
        cleaned_content = clean_body_content(
            all_opinions_soup.getText(separator=" ", strip=True)
        )
        possible_clusters = OpinionCluster.objects.filter(
            citations__reporter=citation.corrected_reporter(),
            citations__volume=citation.groups["volume"],
            citations__page=citation.groups["page"],
        ).order_by("id")

        match = match_based_text(
            cleaned_content,
            docket_number,
            case_name,
            possible_clusters,
            case_name_short,
            citation,
        )

        if match:
            return match

        possible_clusters = (
            OpinionCluster.objects.filter(
                date_filed=data["date_filed"],
                docket__court_id=data["court_id"],
            )
            .exclude(citations__reporter=citation.corrected_reporter())
            .order_by("id")
        )
        match = match_based_text(
            cleaned_content,
            docket_number,
            case_name,
            possible_clusters,
            case_name_short,
            citation,
        )

        if match:
            return match

        month = timedelta(days=31)
        possible_clusters = (
            OpinionCluster.objects.filter(
                date_filed__range=[
                    data["date_filed"] - month,
                    data["date_filed"] + month,
                ],
                docket__court_id=data["court_id"],
            )
            .exclude(citations__reporter=citation.corrected_reporter())
            .exclude(date_filed=data["date_filed"])
            .order_by("id")
        )
        match = match_based_text(
            cleaned_content,
            docket_number,
            case_name,
            possible_clusters,  # type: ignore
            case_name_short,
            citation,
        )

        if match:
            return match

    return None


def add_new_case(item: dict) -> None:
    """Add a new case

    Create new docket, cluster, opinions and citations

    :param item: dict with data to add new case
    :return: None
    """

    docket = Docket(
        source=Docket.COLUMBIA,
        date_argued=item["date_argued"],
        date_reargued=item["date_reargued"],
        date_cert_granted=item["date_cert_granted"],
        date_cert_denied=item["date_cert_denied"],
        date_reargument_denied=item["date_reargument_denied"],
        court_id=item["court_id"],
        case_name_short=item["case_name_short"] or "",
        case_name=item["case_name"] or "",
        case_name_full=item["case_name_full"] or "",
        docket_number=(
            clean_docket_number(item["docket_number"])
            if item["docket_number"]
            else None
        ),
    )

    cluster = OpinionCluster(
        judges=item.get("judges", "") or "",
        precedential_status=(
            "Published" if item["published"] else "Unpublished"
        ),
        date_filed=item["date_filed"],
        case_name_short=item["case_name_short"] or "",
        case_name=item["case_name"] or "",
        case_name_full=item["case_name_full"] or "",
        source=SOURCES.COLUMBIA_ARCHIVE,
        attorneys=item["attorneys"] or "",
        posture=item["posture"] or "",
        syllabus=(
            convert_columbia_html(item["syllabus"], opinion_index=99)
            if item.get("syllabus")
            else ""
        ),
    )

    new_opinions = []
    for opinion_info in item["opinions"]:
        author = async_to_sync(lookup_judge_by_last_name)(
            opinion_info["byline"], item["court_id"], item["panel_date"], True
        )

        opinion = Opinion(
            author=author,
            author_str=(
                titlecase(opinion_info["byline"])
                if opinion_info["byline"]
                else ""
            ),
            per_curiam=opinion_info["per_curiam"],
            type=opinion_info["type"],
            html_columbia=convert_columbia_html(
                opinion_info["opinion"], opinion_info["order"]
            ),
            sha1=opinion_info["sha1"],
            local_path=opinion_info["local_path"],
        )

        new_opinions.append(opinion)

    with transaction.atomic():
        docket.save()
        cluster.docket = docket
        cluster.save(index=False)

        for opinion in new_opinions:
            opinion.cluster = cluster
            opinion.save(index=False)

        if item["panel"]:
            update_cluster_panel(cluster, item["panel"], item["panel_date"])

        add_citations_to_cluster(item["citations"], cluster.id)

        domain = "https://www.courtlistener.com"

        logger.info(f"Created item at: {domain}{cluster.get_absolute_url()}")


def import_opinion(filepath: str) -> None:
    """Try to import xml opinion from columbia

    :param filepath: specified path to xml file
    :return: None
    """
    try:
        logger.info(msg=f"Importing case from {filepath}")
        soup = read_xml_to_soup(filepath)
    except UnicodeDecodeError:
        logger.warning(f"UnicodeDecodeError: {filepath}")
        return

    outer_opinion = soup.find("opinion")
    extracted_opinions = extract_columbia_opinions(outer_opinion)
    opinions = process_extracted_opinions(extracted_opinions)
    map_opinion_types(opinions)

    # Add the same sha1 and path values to every opinion (multiple opinions
    # can come from a single XML file).
    sha1 = sha1_of_file(filepath)
    for opinion in opinions:
        opinion["sha1"] = sha1
        opinion["local_path"] = filepath

    # Prepare data
    panel_tags = "".join(fetch_simple_tags(soup, "panel"))
    reporter_captions = "".join(fetch_simple_tags(soup, "reporter_caption"))
    captions = "".join(fetch_simple_tags(soup, "caption"))
    syllabus = "\n".join(
        [s.decode_contents() for s in soup.findAll("syllabus")]
    )
    docket_number = "".join(fetch_simple_tags(soup, "docket")) or None
    attorneys = "\n".join(fetch_simple_tags(soup, "attorneys"))
    posture = "".join(fetch_simple_tags(soup, "posture"))
    courts = get_court_id(" ".join(fetch_simple_tags(soup, "court")))

    columbia_data: dict = {
        "published": is_opinion_published(soup),
        "file": filepath,
        "attorneys": attorneys,
        "citations": fetch_simple_tags(soup, "citation"),
        "docket_number": docket_number,
        "panel": extract_judge_last_name(panel_tags),
        "posture": posture,
        "case_name": format_case_name(reporter_captions),
        "case_name_full": format_case_name(captions),
        "case_name_short": CASE_NAME_TWEAKER.make_case_name_short(
            format_case_name(reporter_captions)
        ),
        "judges": find_judges(opinions),
        "courts": courts,
        "court_id": "",
        "syllabus": syllabus,
        "opinions": opinions,
    }

    # Add date data into columbia dict
    columbia_data.update(find_dates_in_xml(soup))

    if not columbia_data["opinions"]:
        logger.warning(
            f"There is no opinion in the file: {columbia_data['file']}"
        )
        return

    if not columbia_data["courts"]:
        logger.warning(
            f"Failed to find a court ID for: \"{', '.join(fetch_simple_tags(soup, 'court'))}\""
        )
        return

    if len(columbia_data["courts"]) == 1:
        columbia_data["court_id"] = columbia_data["courts"][0]
    else:
        logger.warning(
            f"Multiple matches found for court: \"{', '.join(fetch_simple_tags(soup, 'court'))}\""
        )
        return

    if not Court.objects.filter(id=columbia_data["court_id"]).exists():
        logger.warning(
            f"Court doesn't exist in CourtListener with id: {columbia_data['court_id']}"
        )
        return

    if not columbia_data["date_filed"]:
        logger.warning(
            f"Failed to get a filed date for: {columbia_data['file']}"
        )
        return

    valid_citations = []
    for citation in columbia_data["citations"]:
        cites = get_citations(citation)
        if (
            cites
            and isinstance(cites[0], FullCaseCitation)
            and cites[0].groups.get("volume", False)
        ):
            valid_citations.append(cites[0])

    if not valid_citations:
        logger.warning(
            f"Failed to get a valid citation for: {columbia_data['file']}"
        )
        return

    try:
        possible_match = find_duplicates(columbia_data, valid_citations)
    except ZeroDivisionError:
        logger.warning(
            f"It is not possible to find duplicates, the opinion is probably "
            f"empty in the columbia file: {filepath}"
        )
        return

    if possible_match:
        # Log a message if we have a possible match, avoid adding
        # incorrect data
        logger.info(
            f"Match found: {possible_match.pk} for columbia file: {filepath}"
        )
        return

    # No match for the file, create new case
    add_new_case(columbia_data)


def parse_columbia_opinions(options: dict) -> None:
    """Try to import each opinion from csv file

    :param options: options passed from management command
    :return: None
    """
    csv_filepath, xml_dir = options["csv_file"], options["xml_dir"]
    skip_until, limit = options["skip_until"], options["limit"]
    total_processed = 0
    start = False if skip_until else True

    logger.info(f"Loading csv file at {csv_filepath}")
    data = pd.read_csv(csv_filepath, delimiter=",", dtype={"filepath": str})

    for index, item in data.iterrows():
        filepath = item["filepath"]

        if not start and skip_until in filepath:
            start = True
        if not start:
            continue

        # filepath example: indiana/court_opinions/documents/2713f39c5a8e8684.xml
        xml_path = os.path.join(xml_dir, filepath)
        if not os.path.exists(xml_path):
            logger.warning(f"No file at: {xml_path}")
            continue

        import_opinion(
            filepath=xml_path,
        )

        total_processed += 1

        if total_processed % 10000 == 0:
            logger.info(f"Files imported: {total_processed}")

        if limit and total_processed >= limit:
            logger.info(f"Finished {limit} imports")
            return


class Command(VerboseCommand):
    help = (
        "Parses the xml files in the specified csv file into opinion objects that are "
        "saved in the database."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-until",
            type=str,
            help="Start after specified filename. e.g. 2713f39c5a8e8684.xml",
            required=False,
        )

        parser.add_argument(
            "--csv-file",
            default="/opt/courtlistener/_columbia/columbia_import.csv",
            help="Csv file with xml filepaths to import.",
            required=False,
        )

        parser.add_argument(
            "--limit",
            default=10000,
            type=int,
            help="Limit number of files to import",
            required=False,
        )

        parser.add_argument(
            "--xml-dir",
            default="/opt/courtlistener/_columbia",
            required=False,
            help="The absolute path to the directory with columbia xml files",
        )

    def handle(self, *args, **options) -> None:
        parse_columbia_opinions(options)
