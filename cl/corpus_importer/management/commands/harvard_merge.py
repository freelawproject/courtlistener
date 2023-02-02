import datetime
import itertools
import json
import logging
from typing import Any, Dict, Tuple

from bs4 import BeautifulSoup
from django.db import transaction
from juriscraper.lib.string_utils import titlecase
from lxml.html import fromstring

from cl.corpus_importer.management.commands.harvard_opinions import (
    parse_extra_fields,
    validate_dt,
)
from cl.corpus_importer.utils import match_lists
from cl.lib.command_utils import VerboseCommand
from cl.lib.string_diff import get_cosine_similarity
from cl.people_db.lookup_utils import extract_judge_last_name
from cl.search.models import Docket, Opinion, OpinionCluster


def read_json(cluster_id: str) -> Dict[str, Any] | None:
    """Helper method to read json into object

    :param cluster_id: the cluster to fetch the filepath for
    :return: Harvard data as a json object or None
    """
    cluster = OpinionCluster.objects.get(id=cluster_id)
    if cluster.filepath_json_harvard:
        return json.load(cluster.filepath_json_harvard)
    return None


def fetch_non_harvard_data(harvard_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get data from harvard casebody and preprocess

    :param harvard_data:
    :return: dict with values extracted from casebody
    """
    soup = BeautifulSoup(harvard_data["casebody"]["data"], "lxml")

    # Some documents contain images in the HTML
    # Flag them for a later crawl by using the placeholder '[[Image]]'
    judge_list = [
        extract_judge_last_name(x.text) for x in soup.find_all("judges")
    ]
    author_list = [
        extract_judge_last_name(x.text) for x in soup.find_all("author")
    ]
    # Flatten and dedupe list of judges
    judges = ", ".join(
        sorted(
            list(set(itertools.chain.from_iterable(judge_list + author_list)))
        )
    )
    judges = titlecase(judges)
    # docket_string = harvard_data["docket_number"].strip()
    all_data = {"judges": judges}
    short_fields = ["attorneys", "disposition", "otherdate", "seealso"]
    long_fields = [
        "syllabus",
        "summary",
        "history",
        "headnotes",
        "correction",
    ]
    short_data = parse_extra_fields(soup, short_fields, False)
    long_data = parse_extra_fields(soup, long_fields, True)
    all_data.update(short_data)
    all_data.update(long_data)
    all_data = {k: v for k, v in all_data.items() if v}
    return all_data


def combine_non_overlapping_data(
    cluster_id: str, harvard_data: Dict[str, Any]
) -> Dict[str, Tuple]:
    """Combine non overlapping data and return dictionary of data for merging

    :param cluster_id: Cluster id to merge
    :param harvard_data: The harvard data as json
    :return: Optional dictionary of data to continue to merge
    """
    opinion_cluster = OpinionCluster.objects.get(id=cluster_id)
    all_data = fetch_non_harvard_data(harvard_data)
    clean_dictionary = {}
    for key, value in all_data.items():
        cl_value = getattr(opinion_cluster, key)
        if not cl_value:
            OpinionCluster.objects.filter(id=cluster_id).update(**{key: value})
        else:
            if value != cl_value:
                clean_dictionary[key] = (value, cl_value)
    return clean_dictionary


def merge_long_fields(cluster_id: str, field_name: str,
                      overlapping_data: Tuple[str, str]) -> None:
    """Merge two long text fields

    :param cluster_id: Cluster id to update
    :param field_name: field name to update in opinion cluster
    :param overlapping_data: data to compare from harvard and courtlistener
    :return: None
    """
    harvard_data, cl_data = overlapping_data[0], overlapping_data[1]
    # Do some text comparison
    similarity = get_cosine_similarity(harvard_data, cl_data)
    if similarity < 0.9:
        # they are not too similar, choose the larger one
        if len(harvard_data) > len(cl_data):
            OpinionCluster.objects.filter(id=cluster_id).update(
                **{field_name: harvard_data}
            )


def merge_judges(cluster_id: str, field_name: str,
                 overlapping_data: Tuple[str, str],
                 judges_raw_data: str) -> None:
    """Merge overlapping judge values

    :param cluster_id: Cluster id to update
    :param field_name: field name to update in opinion cluster
    :param overlapping_data: data to compare from harvard and courtlistener
    :param judges_raw_data: unprocessed judges data
    :return: None
    """
    harvard_data, cl_data = overlapping_data[0], overlapping_data[1]
    # let's normalize cl data, if it is already normalized, we will
    # get similar string, if not, then this is a good chance to
    # do it and then compare
    judges_last_names = [extract_judge_last_name(cl_data)]
    # Flatten and dedupe list of judges
    judges = ", ".join(
        sorted(list(set(itertools.chain.from_iterable(judges_last_names))))
    )
    cl_data = titlecase(judges)
    similarity = get_cosine_similarity(harvard_data, cl_data)
    cl_judges_count = len(judges.split(", "))
    harvard_judges_count = len(harvard_data.split(", "))
    if 0.37 <= similarity <= 0.81:
        if harvard_judges_count == 1 and cl_judges_count == 1:
            # There is only one judge, get raw value from object
            opinion_cluster_judges = OpinionCluster.objects.get(
                id=cluster_id).judges
            if len(judges_raw_data) > len(opinion_cluster_judges):
                # Judges data in harvard is better than the one in CL
                OpinionCluster.objects.filter(id=cluster_id).update(
                    **{field_name: titlecase(judges_raw_data)}
                )

        elif harvard_judges_count > cl_judges_count:
            # Harvard judges count is bigger than cl count, then update judges
            OpinionCluster.objects.filter(id=cluster_id).update(
                **{field_name: harvard_data}
            )
    elif similarity >= 1.0:
        # Both names are similar because were preprocessed, but lets use raw
        # string from harvard and cl to pick the best
        if harvard_judges_count == 1 and cl_judges_count == 1:
            # There is only one judge, use raw strings to pick best
            opinion_cluster_judges = OpinionCluster.objects.get(
                id=cluster_id).judges
            if len(judges_raw_data) > len(opinion_cluster_judges):
                # Judges data in harvard is better than the one in CL
                OpinionCluster.objects.filter(id=cluster_id).update(
                    **{field_name: titlecase(judges_raw_data)}
                )


def merge_dates(cluster_id: str, field_name: str,
                overlapping_data: Tuple[str, datetime.date]) -> None:
    """Compare two dates and choose the best to update the opinion cluster
    the value if one value is better than the other

    :param cluster_id: Cluster id to update
    :param field_name: field name to update in opinion cluster
    :param overlapping_data: data to compare
    :return: None
    """
    harvard_data = overlapping_data[0]
    cluster = OpinionCluster.objects.filter(id=cluster_id).first()
    harvard_date, harvard_date_is_approximate = validate_dt(harvard_data)
    if cluster.date_filed_is_approximate and not harvard_date_is_approximate:
        # if harvard date is not approximate, it should be better
        OpinionCluster.objects.filter(id=cluster_id).update(
            **{field_name: harvard_date}
        )


def merge_strings(cluster_id: str, field_name: str,
                  overlapping_data: Tuple[str, str]) -> None:
    """Compare two strings and choose the largest

    :param cluster_id: Cluster id to update
    :param field_name: field name to update in opinion cluster
    :param overlapping_data: data to compare from harvard and courtlistener
    :return: None
    """
    harvard_data, cl_data = overlapping_data[0], overlapping_data[1]
    if len(harvard_data) > len(cl_data):
        OpinionCluster.objects.filter(id=cluster_id).update(
            **{field_name: harvard_data}
        )


def merge_bool_values(cluster_id: str, field_name: str,
                      overlapping_data: Tuple[bool, bool]) -> None:
    """Compare two boolean values and update the value in opinion cluster
    if this changed

    :param cluster_id: Cluster id to update
    :param field_name: field name to update in opinion cluster
    :param overlapping_data: data to compare from harvard and courtlistener
    :return: None
    """
    harvard_data, cl_data = overlapping_data[0], overlapping_data[1]
    if harvard_data != cl_data:
        # Boolean value changed, keep the one in harvard data
        OpinionCluster.objects.filter(id=cluster_id).update(
            **{field_name: harvard_data}
        )


def get_judges_data(harvard_data: Dict[str, Any]) -> str:
    """Get judges raw data from harvard data

    :param harvard_data: json data from harvard case
    :return: string with unprocessed ajudges from harvard data
    """
    soup = BeautifulSoup(harvard_data["casebody"]["data"], "lxml")

    # List of unprocessed judges names
    judge_unprocessed_list = [
        x.text for x in soup.find_all("judges")
    ]

    # List of unprocessed authors names
    author_unprocessed_list = [
        x.text for x in soup.find_all("author")
    ]

    # Remove duplicates and join all names
    judges_str = ", ".join(
        sorted(
            list(set(judge_unprocessed_list + author_unprocessed_list))
        )
    )

    return judges_str


def merge_opinion_clusters(cluster_id: str) -> None:
    """Merge opinion cluster, docket and opinion data from Harvard

    :param cluster_id: The cluster ID to merger
    :return: None
    """
    harvard_data = read_json(cluster_id)
    if harvard_data:
        with transaction.atomic():
            map_and_merge_opinions(cluster_id, harvard_data)
            clean_dictionary = combine_non_overlapping_data(
                cluster_id, harvard_data
            )
            if clean_dictionary != {}:
                logging.info(f"Merging complete for: {cluster_id}")

            long_fields = [
                "syllabus",
                "summary",
                "history",
                "headnotes",
                "correction",
            ]

            # TODO what about case name fields, date filed or docker number
            #  field from harvard?

            for field_name in clean_dictionary.keys():
                if field_name in long_fields.extend(["disposition"]):
                    merge_long_fields(
                        cluster_id, field_name,
                        clean_dictionary.get(field_name)
                    )
                elif field_name in ["date_filed", "otherdate"]:
                    merge_dates(cluster_id, field_name,
                                clean_dictionary.get(field_name))
                elif field_name == "judges":
                    judges_data = get_judges_data(harvard_data)
                    merge_judges(cluster_id, field_name,
                                 clean_dictionary.get(field_name), judges_data)
                elif field_name == "attorneys":
                    merge_strings(cluster_id, field_name,
                                  clean_dictionary.get(field_name))
                else:
                    logging.info(
                        f"Field not considered in the proccess: {field_name}"
                    )
    else:
        logging.info(f"Cluster id: {cluster_id} doesn't have a json file.")


def start_merger(cluster_id=None) -> None:
    """Start the merger

    Query the database for a list of opinions that have not been merged yet
    :param cluster_id: Cluster ID if available
    :return: None
    """
    if cluster_id:
        cluster_ids = [cluster_id]
    else:
        sources_without_harvard = [
            source[0]
            for source in Docket.SOURCE_CHOICES
            if "Harvard" not in source[1]
        ]
        cluster_ids = OpinionCluster.objects.filter(
            docket__source__in=sources_without_harvard,
            filepath_json_harvard__isnull=False,
        ).values_list("id", flat=True)

    for cluster_id in cluster_ids:
        merge_opinion_clusters(cluster_id=cluster_id)


def fetch_cl_opinion_content(sub_opinions: [Opinion]) -> [str]:
    """Fetch CL opinion Content

    This is a simple helper function to grab an opinion content to compare
    against the harvard xml
    :param sub_opinions: Sub opinions for a cluster
    :return: Opinion text as a list
    """
    cl_opinions = []
    for sub_opinion in sub_opinions:
        for name in (
            "html_columbia",
            "html_with_citations",
            "html",
            "html_lawbox",
            "plain_text",
        ):
            op_type = name
            opinion_content = getattr(sub_opinion, name)
            if not opinion_content:
                continue
            break
        if "html" in op_type:
            html = fromstring(opinion_content)
            opinion_content = html.text_content()
        cl_opinions.append(opinion_content)
    return cl_opinions


def map_and_merge_opinions(cluster: str, harvard_data: Dict[str, Any]) -> None:
    """Map and merge opinion data

    :param cluster: Cluster ID
    :param harvard_data: json data from harvard case
    :return: None
    """
    # TODO also handle authors ... here.... okay.
    used_combined_opinions = False
    case_body = harvard_data["casebody"]["data"]

    sub_opinions = Opinion.objects.filter(cluster__id=cluster)
    harvard_html = fromstring(case_body.encode()).xpath(".//opinion")
    harvard_opinions = [op.text_content() for op in harvard_html]
    cl_opinions = fetch_cl_opinion_content(sub_opinions=sub_opinions)
    if len(harvard_opinions) != len(cl_opinions):
        used_combined_opinions = True

        # crashes without a sub opinion ... that makes sense
        matches = match_lists(harvard_opinions, cl_opinions)
        if not matches:
            used_combined_opinions = True

        if not used_combined_opinions:
            for k, v in matches.items():
                op = sub_opinions[k]
                op.xml_harvard = harvard_opinions[v]
                op.save()

    if used_combined_opinions:
        Opinion.objects.create(
            xml_harvard=case_body,
            cluster=OpinionCluster.objects.get(id=cluster),
            type="010combined",
        )


class Command(VerboseCommand):
    help = "Merge harvard opinions into CL opinions"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--cluster-id",
            type=str,
            help="The cluster id to merge",
            required=False,
        )
        parser.add_argument(
            "--no-debug",
            action="store_true",
            help="Turn off debug logging",
        )

    def handle(self, *args, **options) -> None:
        if options["no_debug"]:
            logging.disable(logging.DEBUG)
