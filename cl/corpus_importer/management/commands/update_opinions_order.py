import os.path
import re
from typing import Any, List, Optional

from bs4 import BeautifulSoup, NavigableString, Tag
from django.core.management import BaseCommand
from django.db.models import Count

from cl.corpus_importer.utils import similarity_scores
from cl.lib.command_utils import logger
from cl.lib.string_diff import get_cosine_similarity
from cl.search.models import SOURCES, Opinion, OpinionCluster

VALID_COLUMBIA_SOURCES = [
    key
    for key in dict(SOURCES.NAMES).keys()
    if SOURCES.COLUMBIA_ARCHIVE in key
]

VALID_HARVARD_SOURCES = [
    key for key in dict(SOURCES.NAMES).keys() if SOURCES.HARVARD_CASELAW in key
]


# TODO remove the funcitions below and import them from utils.py and columbia_utils.py when those changes get merged


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


class EmptyOpinionException(Exception):
    """An exception for opinions that raise a ZeroDivisionError Exception due empty
    opinion tag or empty opinion content in cl"""

    def __init__(self, message: str) -> None:
        self.message = message


def read_xml_to_soup(filepath: str) -> BeautifulSoup:
    """This function reads the xml file, fixes the bad tags in columbia xml
    files and returns a BeautifulSoup object

    :param filepath: path to xml file
    :return: BeautifulSoup object of parsed content
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


def add_floating_opinion(
    opinions: list, floating_content: list, opinion_order: int
) -> list:
    """We have found floating opinions in bs object, we keep the opinion
    content as a new opinion

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
    """We extract all possible opinions from BeautifulSoup, with and without
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


def merge_opinions(
    opinions: list, content: list, current_order: int
) -> tuple[list, int]:
    """Merge last and previous opinion if are the same type or create a new
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


def process_extracted_opinions(extracted_opinions: list) -> list:
    """We read the extracted data in extract_opinions function to merge all
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


# TODO ------------------------ remove until here -------------------------------


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
        prep_text = re.sub(
            " +", " ", " ".join(opinion_text.split("\n"))
        ).strip()
        prep_text = re.sub(r"[^a-zA-Z0-9 ]", "", prep_text.lower())

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
        opinion_text = re.sub(
            " +", " ", " ".join(opinion_text.split("\n"))
        ).strip()
        cleaned_opinion = re.sub(r"[^a-zA-Z0-9 ]", "", opinion_text.lower())
        op["opinion"] = cleaned_opinion

    return opinions


def sort_harvard_opinions(start_id: int, end_id: int) -> None:
    """We assume that harvard data is already ordered, we just need to fill the order
    field in each opinion

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

            matches = match_text_lists(
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

                failed = False
                for file_pos, cl_pos in matches.items():
                    # file_pos is the correct index to find the opinion id to update
                    file_opinion = extracted_columbia_opinions[file_pos]
                    # the order was calculated using the xml file
                    file_order = file_opinion.get("order") + start_position
                    cl_opinion = cl_cleaned_opinions[cl_pos]
                    opinion_id_to_update = cl_opinion.get("id")

                    if opinion_id_to_update:
                        try:
                            # Save opinion
                            op = Opinion.objects.get(id=opinion_id_to_update)
                            op.order = file_order
                            op.save()
                            logger.info(
                                f"Cluster id processed: {cluster_id} Update opinion id: {opinion_id_to_update} with position: {file_order}"
                            )
                        except Opinion.DoesNotExist:
                            logger.warning(
                                f"We can't update opinion, opinion doesn't exist with "
                                f"id: {opinion_id_to_update}"
                            )
                            failed = True
                            break
                    else:
                        logger.warning(
                            f"We can't update opinion, empty opinion id "
                            f"from cluster: {cluster_id}"
                        )
                        failed = True
                        break

                if cluster_has_combined_opinion and not failed:
                    combined_opinions_cluster = Opinion.objects.filter(
                        cluster_id=cluster_id, type="010combined"
                    ).order_by("id")

                    # Show combined opinions at beginning
                    for opinion_order, cluster_op in enumerate(
                        combined_opinions_cluster
                    ):
                        cluster_op.order = opinion_order
                        cluster_op.save()

            else:
                # No matches found
                logger.warning(
                    f"Failed to match opinions from cluster id: {cluster_id}"
                )
                continue


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
        if options["process_harvard"] and options["process_columbia"]:
            print(
                "You can only select one option process-harvard or process-columbia"
            )
            return

        if not options["process_harvard"] and not options["process_columbia"]:
            print("One option required: process-harvard or process-columbia")
            return

        if options["process_harvard"]:
            sort_harvard_opinions(options["start_id"], options["end_id"])

        if options["process_columbia"] and options["xml_dir"]:
            sort_columbia_opinions(
                options["start_id"], options["end_id"], options["xml_dir"]
            )

        if options["process_columbia"] and not options["xml_dir"]:
            print(
                "Argument --xml-dir required to read xml files from mounted directory"
            )
