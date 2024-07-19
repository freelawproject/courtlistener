import os.path
import re
from typing import Optional

from bs4 import BeautifulSoup
from django.core.management import BaseCommand
from django.db import transaction
from django.db.models import Count

from cl.corpus_importer.import_columbia.columbia_utils import (
    extract_columbia_opinions,
    map_opinion_types,
    process_extracted_opinions,
    read_xml_to_soup,
)
from cl.corpus_importer.utils import EmptyOpinionException, match_opinion_lists
from cl.lib.command_utils import logger
from cl.search.models import SOURCES, Opinion, OpinionCluster

VALID_COLUMBIA_SOURCES = [
    key
    for key in dict(SOURCES.NAMES).keys()
    if SOURCES.COLUMBIA_ARCHIVE in key
]

VALID_HARVARD_SOURCES = [
    key for key in dict(SOURCES.NAMES).keys() if SOURCES.HARVARD_CASELAW in key
]


def clean_opinion_content(text: str) -> str:
    """Clean opinion content

    :param text: text to clean
    :return: cleaned text
    """

    # Replace line breaks with spaces and get rid of double spaces
    text = re.sub(" +", " ", " ".join(text.split("\n"))).strip()

    # Remove non-alphanumeric and non-whitespace characters from lowercased text
    return re.sub(r"[^a-zA-Z0-9 ]", "", text.lower())


def get_opinions_cleaned_content(
    cluster_id,
) -> tuple[Optional[str], list[dict], int, bool]:
    """Get cleaned opinions content for a cluster object

    :param cluster_id: Cluster ID for a set of opinions
    :return: (xml path, list of extracted opinions, start position, True if combined
    opinions exists in cluster)
    """
    cl_cleaned_opinions = []
    # by default the opinions are ordered by pk
    opinions_from_cluster = Opinion.objects.filter(
        cluster_id=cluster_id
    ).order_by("id")
    combined_opinions_cluster = opinions_from_cluster.filter(
        type="010combined"
    )
    xml_path = None
    cluster_has_combined_opinion = False
    if combined_opinions_cluster:
        # the combined opinion will be displayed at beginning
        start_position = combined_opinions_cluster.count()
        cluster_has_combined_opinion = True
    else:
        # we don't have combined opinions, we start ordering from 0 to n
        start_position = 0

    for i, op in enumerate(opinions_from_cluster.exclude(type="010combined")):
        if op.local_path and not xml_path:
            xml_path = str(op.local_path)

        content = None

        # We can only use columbia's content to infer the ordering
        if len(op.html_columbia) > 1:
            content = op.html_columbia

        if not content:
            raise EmptyOpinionException(
                "There is no content in html_columbia field"
            )

        soup = BeautifulSoup(content, features="html.parser")
        opinion_text = soup.getText(separator=" ", strip=True)
        prep_text = clean_opinion_content(opinion_text)

        cl_cleaned_opinions.append(
            {
                "id": op.id,
                "byline": op.author_str,
                "type": op.type,
                "opinion": prep_text,
                "order": i,
            }
        )

    return (
        xml_path,
        cl_cleaned_opinions,
        start_position,
        cluster_has_combined_opinion,
    )


def fix_filepath(filepath: str) -> str:
    """Fix filepath from file field

    :param filepath: path from file field
    :return: new file path
    """
    if "/home/mlissner/columbia/opinions/" in filepath:
        filepath = filepath.replace("/home/mlissner/columbia/opinions/", "")
    return filepath


def get_opinions_columbia_file(xml_filepath: str) -> list:
    """Get opinions from columbia xml file and convert it into dict

    :param xml_filepath: path of xml file
    :return: dict with data
    """
    soup = read_xml_to_soup(xml_filepath)

    # Find the outer <opinion> tag to have all elements inside
    outer_opinion = soup.find("opinion")

    extracted_opinions = extract_columbia_opinions(outer_opinion)
    opinions = process_extracted_opinions(extracted_opinions)
    map_opinion_types(opinions)

    for op in opinions:
        opinion_content = op.get("opinion")
        soup = BeautifulSoup(opinion_content, "html.parser")
        opinion_text = soup.getText(separator=" ", strip=True)
        cleaned_opinion = clean_opinion_content(opinion_text)
        op["opinion"] = cleaned_opinion

    return opinions


def sort_harvard_opinions(start_id: int, end_id: int) -> None:
    """We assume that harvard data is already ordered, we just need to fill the order
    field in each opinion

    The harvard importer created the opinions in order of appearance in the file

    :param start_id: skip any id lower than this value
    :param end_id: skip any id greater than this value
    :return: None
    """

    # Get all harvard clusters with more than one opinion
    clusters = (
        OpinionCluster.objects.prefetch_related("sub_opinions")
        .annotate(opinions_count=Count("sub_opinions"))
        .filter(opinions_count__gt=1, source__in=VALID_HARVARD_SOURCES)
        .order_by("id")
    )

    if start_id:
        clusters = clusters.filter(pk__gte=start_id)

    if end_id:
        clusters = clusters.filter(pk__lte=end_id)

    # cluster_id: 4697264, the combined opinion will go to the last position
    for oc in clusters:
        logger.info(f"Processing cluster id: {oc}")
        combined_opinions_cluster = oc.sub_opinions.filter(
            type="010combined"
        ).order_by("id")
        if combined_opinions_cluster:
            # the combined opinion will be displayed at first
            start_position = combined_opinions_cluster.count()
        else:
            # we don't have combined opinions, we start ordering from 0 to n
            start_position = 0

        for opinion_order, cluster_op in enumerate(
            oc.sub_opinions.exclude(type="010combined").order_by("id"),
            start=start_position,
        ):
            cluster_op.order = opinion_order
            cluster_op.save()

        # Show combined opinions at beginning
        for opinion_order, cluster_op in enumerate(combined_opinions_cluster):
            cluster_op.order = opinion_order
            cluster_op.save()

        logger.info(msg=f"Opinions reordered for cluster id: {oc.id}")


def update_opinions(
    cluster_id: int,
    cl_opinions: list,
    columbia_opinions: list,
    matches: dict,
    cluster_has_combined_opinion: bool,
    start_position: int,
):
    """Update opinions with correct order

    :param cluster_id:
    :param cl_opinions: a list with cleaned opinions from cl
    :param columbia_opinions: a ordered list with cleaned opinions from xml file
    :param matches: a dict with the matches of each opinion of both lists
    :param cluster_has_combined_opinion: True if the cluster has combined opinions
    :param start_position: the number from where the order should begin for
    non-combined opinions
    :return: None
    """
    update_failed = False

    with transaction.atomic():
        for file_pos, cl_pos in matches.items():
            # file_pos is the correct index to find the opinion id to update
            file_opinion = columbia_opinions[file_pos]
            # the order was calculated using the xml file
            file_order = file_opinion.get("order") + start_position
            cl_opinion = cl_opinions[cl_pos]
            opinion_id_to_update = cl_opinion.get("id")

            if opinion_id_to_update:
                try:
                    # Update opinion order
                    op = Opinion.objects.get(id=opinion_id_to_update)
                    op.order = file_order
                    op.save()
                except Opinion.DoesNotExist:
                    # This should not happen, but it is better to be
                    # cautious
                    logger.warning(
                        f"We can't update opinion, opinion doesn't exist "
                        f"with id: {opinion_id_to_update}"
                    )
                    update_failed = True
                    break

        if cluster_has_combined_opinion and not update_failed:
            combined_opinions_cluster = Opinion.objects.filter(
                cluster_id=cluster_id, type="010combined"
            ).order_by("id")

            # Show combined opinions at beginning
            for opinion_order, cluster_op in enumerate(
                combined_opinions_cluster
            ):
                cluster_op.order = opinion_order
                cluster_op.save()

        if update_failed:
            # There was an error updating an opinion, rollback all changes for
            # cluster's opinions
            logger.warning(
                f"There was an error updating the order of opinions of the "
                f"cluster id: {cluster_id}"
            )
            transaction.set_rollback(True)
        else:
            logger.info(
                f"The order of opinions was updated, cluster id: {cluster_id}"
            )


def sort_columbia_opinions(start_id: int, end_id: int, xml_dir: str) -> None:
    """Update opinion ordering for columbia clusters

    :param start_id: skip any id lower than this value
    :param end_id: skip any id greater than this value
    :param xml_dir: absolute path to the directory with columbia xml files
    :return: None
    """

    # Get all columbia cluster ids with more than one opinion
    clusters = (
        OpinionCluster.objects.annotate(opinions_count=Count("sub_opinions"))
        .filter(opinions_count__gt=1, source__in=VALID_COLUMBIA_SOURCES)
        .order_by("id")
        .values_list("id", flat=True)
    )

    if start_id:
        clusters = filter(lambda x: x >= start_id, clusters)

    if end_id:
        clusters = filter(lambda x: x <= end_id, clusters)

    for cluster_id in clusters:
        logger.info(f"Processing cluster id: {cluster_id}")

        try:
            (
                xml_path,
                cl_cleaned_opinions,
                start_position,
                cluster_has_combined_opinion,
            ) = get_opinions_cleaned_content(cluster_id)
        except EmptyOpinionException:
            logger.warning(
                f"At least one of the opinions from cluster id: {cluster_id} is empty."
            )
            continue

        extracted_columbia_opinions = None
        if xml_path:
            fixed_xml_filepath = os.path.join(xml_dir, fix_filepath(xml_path))

            if not os.path.exists(fixed_xml_filepath):
                logger.warning(
                    f"Xml file not found in {fixed_xml_filepath}, cluster id: {cluster_id}"
                )
                continue

            try:
                extracted_columbia_opinions = get_opinions_columbia_file(
                    fixed_xml_filepath
                )
            except UnicodeDecodeError:
                logger.warning(f"Cannot decode file: {fixed_xml_filepath}")
                continue

        if cl_cleaned_opinions and extracted_columbia_opinions:
            columbia_opinions_content = [
                op.get("opinion")
                for op in extracted_columbia_opinions
                if op.get("opinion")
            ]
            cl_opinions_content = [
                op.get("opinion")
                for op in cl_cleaned_opinions
                if op.get("opinion")
            ]

            matches = match_opinion_lists(
                columbia_opinions_content,
                cl_opinions_content,
            )

            if matches:
                if len(matches.values()) != len(set(matches.values())):
                    # We don't have a unique match for each opinion, they were
                    # probably combined incorrectly
                    logger.info(
                        f"We can't infer opinions order for cluster id: {cluster_id}"
                    )
                    # Go to next cluster id
                    continue

                if len(cl_cleaned_opinions) > len(set(matches.values())):
                    # We have more opinions than matches
                    logger.info(
                        f"We couldn't match all cl opinions to the file's "
                        f"content, cluster id: {cluster_id}"
                    )
                    # Go to next cluster id
                    continue

                # Update all opinions order
                update_opinions(
                    cluster_id,
                    cl_cleaned_opinions,
                    extracted_columbia_opinions,
                    matches,
                    cluster_has_combined_opinion,
                    start_position,
                )


class Command(BaseCommand):
    help = "Fill order field in Opinion objects"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--process-harvard",
            action="store_true",
            help="Fix harvard opinions order",
        )

        parser.add_argument(
            "--process-columbia",
            action="store_true",
            help="Fix columbia opinions order",
        )

        parser.add_argument(
            "--xml-dir",
            default="/opt/courtlistener/_columbia",
            required=False,
            help="The absolute path to the directory with columbia xml files",
        )

        parser.add_argument(
            "--start-id",
            type=int,
            default=0,
            help="Start id for a range of clusters (inclusive)",
        )

        parser.add_argument(
            "--end-id",
            type=int,
            default=0,
            help="End id for a range of clusters (inclusive)",
        )

    def handle(self, *args, **options):

        if not options["process_harvard"] and not options["process_columbia"]:
            logger.info(
                "One option required: process-harvard or process-columbia"
            )
            return

        if options["process_harvard"] and options["process_columbia"]:
            logger.info(
                "You can only select one option process-harvard or process-columbia"
            )
            return

        if options["process_harvard"]:
            sort_harvard_opinions(options["start_id"], options["end_id"])

        if options["process_columbia"]:
            sort_columbia_opinions(
                options["start_id"], options["end_id"], options["xml_dir"]
            )
