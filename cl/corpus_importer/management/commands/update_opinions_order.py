import re
from typing import Any, Optional

from bs4 import BeautifulSoup, NavigableString, Tag
from django.core.management import BaseCommand
from django.db.models import Count

from cl.corpus_importer.utils import similarity_scores
from cl.lib.command_utils import logger
from cl.lib.string_diff import get_cosine_similarity
from cl.search.models import Opinion, OpinionCluster

# TODO Should we add a flag to know that the cluster has been processed?


def match_text_lists(
    file_opinions_list: list[str], cl_opinions_list: list[str]
) -> dict[int, Any]:
    """Generate matching lists above threshold
    :param file_opinions_list: Opinions from file
    :param cl_opinions_list: CL opinions
    :return: Matches if found or False
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


def get_opinion_content(
    cluster_id,
) -> tuple[Optional[str], list[dict], int, bool]:
    """Get the opinions content for a cluster object
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
    combined_opinion = False
    if combined_opinions_cluster:
        # the combined opinion will be displayed at beginning
        start_position = combined_opinions_cluster.count()
        combined_opinion = True
    else:
        # we don't have combined opinions, we start ordering from 0 to n
        start_position = 0

    for i, op in enumerate(opinions_from_cluster.exclude(type="010combined")):
        if op.local_path and not xml_path:
            xml_path = op.local_path
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
                    "order": i,
                }
            )

    return xml_path, cl_cleaned_opinions, start_position, combined_opinion


def get_opinions_columbia_xml(xml_filepath: str) -> list:
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

    for op in opinions:
        opinion_content = op.get("opinion")
        opinion_content = BeautifulSoup(
            opinion_content, "html.parser"
        ).getText()
        opinion_content = re.sub(r"[^a-zA-Z0-9 ]", "", opinion_content.lower())
        op["opinion"] = opinion_content

    return opinions


def run_harvard():
    """
    We assume that harvard data is already ordered, we just need to fill the order
    field in each opinion
    """

    # Get all harvard clusters with more than one opinion
    clusters = (
        OpinionCluster.objects.prefetch_related("sub_opinions")
        .annotate(opinions_count=Count("sub_opinions"))
        .filter(opinions_count__gt=1, source="U")
    )
    # print(clusters.query)
    print("clusters", len(clusters))

    # cluster_id: 4697264, the combined opinion will go to the last position
    for oc in clusters:
        combined_opinions_cluster = oc.sub_opinions.filter(
            type="010combined"
        ).order_by("id")
        if combined_opinions_cluster:
            # the combined opinion will be displayed at first
            start_position = combined_opinions_cluster.count()
        else:
            # we don't have combined opinions, we start ordering from 0 to n
            start_position = 0

        print("combined_opinions_cluster", combined_opinions_cluster)
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


def run_columbia():
    """
    Update opinion order for columbia clusters
    """

    # Get all columbia cluster ids with more than one opinion
    clusters = (
        OpinionCluster.objects.annotate(opinions_count=Count("sub_opinions"))
        .filter(opinions_count__gt=1, source="Z")
        .order_by("id")
        .values_list("id")
    )

    for cluster_id in clusters:
        logger.info(f"Processing cluster id: {cluster_id}")
        (
            xml_path,
            cl_cleaned_opinions,
            start_position,
            combined_opinion,
        ) = get_opinion_content(cluster_id)

        columbia_opinions = None
        if xml_path:
            columbia_opinions = get_opinions_columbia_xml(xml_path)

        if cl_cleaned_opinions and columbia_opinions:
            matches = match_text_lists(
                [op.get("opinion") for op in columbia_opinions],
                [op.get("opinion") for op in cl_cleaned_opinions],
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
                    file_opinion = columbia_opinions[file_pos]
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

                if combined_opinion and not failed:
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

    def handle(self, *args, **options):
        print("harvard", options["process_harvard"])
        print("columbia", options["process_columbia"])

        if options["process_harvard"] and options["process_columbia"]:
            print(
                "You can only select one option process-harvard or process-columbia"
            )
            return

        if options["process_harvard"]:
            run_harvard()

        if options["process_columbia"]:
            run_columbia()
