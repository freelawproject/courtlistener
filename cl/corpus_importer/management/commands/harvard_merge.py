import itertools
import json
import logging
from datetime import date
from typing import Any, Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from django.db import transaction
from juriscraper.lib.string_utils import harmonize, titlecase

from cl.corpus_importer.management.commands.harvard_opinions import (
    clean_docket_number,
    parse_extra_fields,
    validate_dt,
)
from cl.corpus_importer.utils import match_lists
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_diff import get_cosine_similarity
from cl.people_db.lookup_utils import extract_judge_last_name
from cl.search.models import SOURCES, Docket, Opinion, OpinionCluster


class AuthorException(Exception):
    """Error found in author merger."""

    def __init__(self, message: str) -> None:
        self.message = message


class JudgeException(Exception):
    """An exception for wrong judges"""

    def __init__(self, message: str) -> None:
        self.message = message


def read_json(cluster_id: int) -> Dict[str, Any] | None:
    """Helper method to read json into object

    :param cluster_id: the cluster to fetch the filepath for
    :return: Harvard data as a json object or None
    """
    cluster = OpinionCluster.objects.get(id=cluster_id)
    if cluster.filepath_json_harvard:
        try:
            local_data = json.load(cluster.filepath_json_harvard)
        except ValueError:
            logger.warning(
                f"Empty json: missing case at: {cluster.filepath_json_harvard.path}"
            )
            return None
        except Exception as e:
            logger.warning(
                f"Unknown error {e} for: {cluster.filepath_json_harvard.path}"
            )
            return None

        identifier = "/".join(
            cluster.filepath_json_harvard.path.rsplit("/", 2)[1:]
        )

        # Fetch fix if exists
        fix = requests.get(
            f"https://raw.githubusercontent.com/freelawproject/opinionated/main/data/harvard/{identifier}",
            timeout=10,
        )
        if fix.status_code == 200:
            local_data.update(fix.json())

        return local_data
    return None


def get_data_source(harvard_data: Dict[str, Any]) -> str:
    """Get json data source: Fastcase or CAP

    The default is CAP/Harvard

    :param harvard_data: case data as dict
    :return: data source
    """
    data_source = "CAP"
    data_provenance = harvard_data.get("provenance")
    if data_provenance:
        data_source = data_provenance.get("source")

    return data_source


def fetch_non_harvard_data(harvard_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get data from harvard casebody and preprocess

    :param harvard_data:
    :return: dict with values extracted from casebody
    """
    soup = BeautifulSoup(harvard_data["casebody"]["data"], "lxml")

    # Some documents contain images in the HTML
    # Flag them for a later crawl by using the placeholder '[[Image]]'
    judge_list = [
        extract_judge_last_name(x.text)
        for x in soup.find_all(
            lambda tag: (tag.name == "judges" and tag.get("data-type") is None)
            or tag.get("data-type") == "judges"
        )
    ]
    author_list = [
        extract_judge_last_name(x.text)
        for x in soup.find_all(
            lambda tag: (tag.name == "author" and tag.get("data-type") is None)
            or tag.get("data-type") == "author"
        )
    ]
    # Flatten and dedupe list of judges
    judges = ", ".join(
        sorted(
            list(set(itertools.chain.from_iterable(judge_list + author_list)))
        )
    )

    judges = titlecase(judges)
    all_data = {"judges": judges}
    short_fields = ["attorneys", "disposition", "otherdate", "seealso"]
    long_fields = [
        "syllabus",
        "summary",
        "history",
        "headnotes",
        "correction",
    ]

    # Find fist opinion element
    first_opinion_at = soup.find("opinion")

    # Find floating footnotes before first opinion
    head_matter_footnotes = first_opinion_at.find_all_previous("footnote")
    if head_matter_footnotes:
        # Combine floating footnotes and add them to the dict,
        # find_all_previous returns elements in reverse order
        combined_floating_footnotes = " ".join(
            str(fn) for fn in reversed(head_matter_footnotes)
        )
        all_data["head_matter_footnotes"] = combined_floating_footnotes

    # Find images from books before first opinion
    book_images = first_opinion_at.find_all_previous(
        lambda tag: tag.get("data-type") == "picture"
        or tag.get("data-type") == "img"
    )
    if book_images:
        all_data["book_images"] = " ".join(
            str(img) for img in reversed(book_images)
        )

    # Combine attorneys and law
    find_fields = soup.find_all(
        lambda tag: tag.get("data-type") == "legal" or tag.name == "attorneys"
    )
    if find_fields:
        # Remove page-number tags to make content more readable
        for e in find_fields:
            if e is not None:
                [x.extract() for x in e.find_all("page-number")]

        # Combine attorneys and legal data-type field
        arguments = " ".join(str(x) for x in find_fields)
        all_data["arguments"] = arguments

    short_data = parse_extra_fields(soup, short_fields, False)

    if "otherdate" in short_data:
        # Rename to correct field name
        short_data["other_dates"] = short_data.pop("otherdate")

    if "seealso" in short_data:
        # Rename to correct field name
        short_data["cross_reference"] = short_data.pop("seealso")

    long_data = parse_extra_fields(soup, long_fields, True)
    all_data.update(short_data)
    all_data.update(long_data)
    all_data = {k: v for k, v in all_data.items() if v}
    return all_data


def combine_non_overlapping_data(
    cluster_id: int, harvard_data: dict
) -> dict[str, Tuple]:
    """Combine non overlapping data and return dictionary of data for merging

    :param cluster_id: Cluster id to merge
    :param harvard_data: The harvard data as json
    :return: Optional dictionary of data to continue to merge
    """
    opinion_cluster = OpinionCluster.objects.get(id=cluster_id)
    all_data = fetch_non_harvard_data(harvard_data)
    changed_values_dictionary: dict[str, Tuple] = {}
    for key, value in all_data.items():
        cl_value = getattr(opinion_cluster, key)
        if not cl_value:
            # Value is empty for key, we can add it directly to the object
            OpinionCluster.objects.filter(id=cluster_id).update(**{key: value})
        else:
            if value != cl_value:
                # We have different values, update dict
                changed_values_dictionary[key] = (value, cl_value)

    return changed_values_dictionary


def merge_long_fields(
    cluster_id: int,
    field_name: str,
    overlapping_data: Optional[Tuple[str, str]],
) -> None:
    """Merge two long text fields

    :param cluster_id: Cluster id to update
    :param field_name: field name to update in opinion cluster
    :param overlapping_data: data to compare from harvard and courtlistener
    :return: None
    """
    if overlapping_data:
        if overlapping_data[0] and overlapping_data[1]:
            harvard_data, cl_data = overlapping_data[0], overlapping_data[1]
            # Do some text comparison
            similarity = get_cosine_similarity(harvard_data, cl_data)
            if similarity < 0.9:
                # they are not too similar, choose the larger one
                if len(harvard_data) > len(cl_data):
                    OpinionCluster.objects.filter(id=cluster_id).update(
                        **{field_name: harvard_data}
                    )
            else:
                pass
                # should we log long data not really being similar?


def merge_judges(
    cluster_id: int,
    overlapping_data: Optional[Tuple[str, str]],
) -> None:
    """Merge overlapping judge values

    :param cluster_id: Cluster id to update
    :param overlapping_data: data to compare from harvard and courtlistener
    :return: None
    """

    if overlapping_data:
        harvard_data, cl_data = overlapping_data

        # Get last names from each source
        cl_clean = set(extract_judge_last_name(cl_data))
        harvard_clean = set(extract_judge_last_name(harvard_data))
        judges = titlecase(", ".join(extract_judge_last_name(harvard_data)))

        if harvard_clean.issuperset(cl_clean) and harvard_clean != cl_clean:
            OpinionCluster.objects.filter(id=cluster_id).update(judges=judges)
        elif not harvard_clean.intersection(cl_clean):
            raise JudgeException("Judges are completely different.")


def merge_cluster_dates(
    cluster_id: int,
    field_name: str,
    overlapping_data: Optional[Tuple[str | None, date]],
) -> None:
    """Compare two dates and choose the best to update the opinion cluster
    the value if one value is better than the other

    :param cluster_id: Cluster id to update
    :param field_name: field name to update in opinion cluster
    :param overlapping_data: data to compare
    :return: None
    """
    if overlapping_data:
        harvard_data, cl_date = overlapping_data
        cluster = OpinionCluster.objects.filter(id=cluster_id).first()
        if harvard_data:
            harvard_date, harvard_date_is_approximate = validate_dt(
                harvard_data
            )
            if cluster.docket.source == Docket.SCRAPER:
                # Give preference to harvard data
                if harvard_date != cl_date:
                    OpinionCluster.objects.filter(id=cluster_id).update(
                        **{field_name: harvard_date}
                    )
            elif (
                cluster.date_filed_is_approximate
                and not harvard_date_is_approximate
            ):
                # For some reason docket source is different, then check if one date is approximate and the other is not if harvard date is not approximate, it should be better
                OpinionCluster.objects.filter(id=cluster_id).update(
                    **{field_name: harvard_date}
                )


def merge_strings(
    cluster_id: int, field_name: str, overlapping_data: Tuple[str, str]
) -> None:
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


def merge_docket_numbers(cluster_id: int, harvard_docket_number: str) -> None:
    """Merge Docket Numbers

    :param cluster_id: The cluster id of the merging item
    :param harvard_docket_number: The harvard docket number
    :return: None
    """
    cl_docket_number = OpinionCluster.objects.get(
        id=cluster_id
    ).docket.docket_number

    if cl_docket_number:
        # Check if docket number exists
        # e.g. CL docket id #3952066 doesn't have
        if cl_docket_number in harvard_docket_number:
            Docket.objects.update(docket_number=harvard_docket_number)
        else:
            cl_clean_docket = clean_docket_number(cl_docket_number)
            h_clean_docket = clean_docket_number(harvard_docket_number)

            # Check if their relatively similar and if so save the harvard one
            # if its longer
            similarity = get_cosine_similarity(cl_clean_docket, h_clean_docket)
            if similarity > 0.8:
                if len(harvard_docket_number) > len(cl_docket_number):
                    Docket.objects.update(docket_number=harvard_docket_number)


def merge_case_names(cluster_id: int, harvard_data: Dict[str, Any]) -> None:
    """Merge case names

    :param cluster_id: The cluster id of the merging item
    :param harvard_data: json data from harvard case
    :return: None
    """
    cluster = OpinionCluster.objects.get(id=cluster_id)
    harvard_case_name = titlecase(harmonize(harvard_data["name_abbreviation"]))
    harvard_case_name_full = titlecase(harvard_data["name"])
    cluster_case_name = titlecase(harmonize(cluster.case_name))
    cluster_case_name_full = titlecase(cluster.case_name_full)

    update_dict = {}
    # Case with full case names
    if not cluster_case_name_full and harvard_case_name_full:
        update_dict["case_name_full"] = harvard_case_name_full
        # Change stored value to new
        cluster_case_name_full = harvard_case_name_full
    elif cluster_case_name_full and harvard_case_name_full:
        if len(harvard_case_name_full) > len(cluster_case_name_full):
            # Select best case name based on string length
            update_dict["case_name_full"] = harvard_case_name_full
            # Change stored value to new
            cluster_case_name_full = harvard_case_name_full
    else:
        # We don't care if harvard data is empty or both are empty
        pass

    # Case with abbreviated case names
    if not cluster_case_name and harvard_case_name:
        update_dict["case_name"] = harvard_case_name
        # Change stored value to new
        cluster_case_name = harvard_case_name
    elif cluster_case_name and harvard_case_name:
        if len(harvard_case_name) > len(cluster_case_name):
            # Select best case name based on string length
            update_dict["case_name"] = harvard_case_name
            # Change stored value to new
            cluster_case_name = harvard_case_name
    else:
        # We don't care if harvard data is empty or both are empty
        pass

    if cluster_case_name_full and cluster_case_name:
        if len(cluster_case_name) > len(cluster_case_name_full):
            # Swap field values
            update_dict["case_name"] = cluster_case_name_full
            update_dict["case_name_full"] = cluster_case_name

    if update_dict:
        OpinionCluster.objects.filter(id=cluster_id).update(**update_dict)


def merge_date_filed(cluster_id: int, harvard_data: dict) -> None:
    """Merge date filed

    :param cluster_id: The cluster id of the merging item
    :param harvard_data: json data from harvard case
    :return: None
    """
    cluster = OpinionCluster.objects.get(id=cluster_id)
    harvard_date_filed = harvard_data.get("decision_date")
    cluster_date_filed = cluster.date_filed
    merge_cluster_dates(
        cluster_id, "date_filed", (harvard_date_filed, cluster_date_filed)
    )


def merge_overlapping_data(
    cluster_id: int, changed_values_dictionary: dict
) -> None:
    """Merge overlapping data

    :param cluster_id: the cluster id
    :param clean_dictionary: the dictionary of data to merge
    :return: None
    """

    if not changed_values_dictionary:
        # Empty dictionary means that we don't have overlapping data
        logger.info(f"Merging complete for: {cluster_id}")
        return

    long_fields = [
        "syllabus",
        "summary",
        "history",
        "headnotes",
        "correction",
        "cross_reference",
        "disposition",
        "head_matter_footnotes",
        "arguments",
        "book_images",
    ]

    for field_name in changed_values_dictionary.keys():
        if field_name in long_fields:
            merge_long_fields(
                cluster_id,
                field_name,
                changed_values_dictionary.get(field_name),
            )
        elif field_name in ["other_dates"]:
            merge_cluster_dates(
                cluster_id,
                field_name,
                changed_values_dictionary.get(field_name),
            )
        elif field_name == "judges":
            merge_judges(
                cluster_id,
                changed_values_dictionary.get(field_name),
            )
        elif field_name == "attorneys":
            merge_strings(
                cluster_id,
                field_name,
                changed_values_dictionary.get(field_name, ""),
            )
        else:
            logger.info(f"Field not considered in the process: {field_name}")


def update_docket_source(cluster_id: int) -> None:
    """Update docket source and complete

    :param cluster_id: the cluster id
    :return: None
    """
    docket = OpinionCluster.objects.get(id=cluster_id).docket
    source = docket.source
    docket.source = Docket.HARVARD + source
    docket.save()


def update_cluster_source(cluster_id: int) -> None:
    """Update cluster source

    :param cluster_id: cluster id to update
    :return: None
    """
    cluster = OpinionCluster.objects.get(id=cluster_id)
    source = cluster.source
    if "U" not in source or source != "U":
        # Cluster source is not harvard or doesn't contain harvard, merge
        # source with harvard
        cluster.source = source + SOURCES.HARVARD_CASELAW
        cluster.save()


def merge_opinion_clusters(
    cluster_id: int, only_fastcase: bool = False
) -> None:
    """Merge opinion cluster, docket and opinion data from Harvard

    :param cluster_id: The cluster ID to merger
    :return: None
    """
    harvard_data = read_json(cluster_id)
    if harvard_data:
        if only_fastcase:
            source = get_data_source(harvard_data)
            if source == "Fastcase":
                logger.info("Skipping non fastcase opinion cluster")
                return
        try:
            with transaction.atomic():
                map_and_merge_opinions(cluster_id, harvard_data)
                changed_values_dictionary = combine_non_overlapping_data(
                    cluster_id, harvard_data
                )
                merge_docket_numbers(cluster_id, harvard_data["docket_number"])
                merge_case_names(cluster_id, harvard_data)
                merge_date_filed(cluster_id, harvard_data)
                merge_overlapping_data(cluster_id, changed_values_dictionary)
                update_docket_source(cluster_id=cluster_id)
                update_cluster_source(cluster_id=cluster_id)
                logger.info(msg=f"Finished merging cluster: {cluster_id}")

        except AuthorException:
            logger.warning(msg=f"Author Exception for cluster {cluster_id}")
        except JudgeException:
            logger.warning(msg=f"Judge exception for: {cluster_id}")
    else:
        logger.warning(msg=f"No Harvard json for cluster: {cluster_id}")


def fetch_cl_opinion_content(sub_opinions: list[Opinion]) -> list[str]:
    """Fetch CL opinion Content

    This is a simple helper function to grab an opinion content to compare
    against the harvard xml
    :param sub_opinions: Sub opinions for a cluster
    :return: Opinion text as a list
    """
    cl_opinions = []

    # Note: harvard importer stores opinion in xml_harvard field, we need to
    # add it to the list
    for sub_opinion in sub_opinions:
        for name in (
            "html_columbia",
            "html_with_citations",
            "html",
            "html_lawbox",
            "plain_text",
            "xml_harvard",
        ):
            op_type = name
            opinion_content = getattr(sub_opinion, name)
            if not opinion_content:
                continue
            break
        if "html" in op_type or op_type == "xml_harvard":
            opinion_content = BeautifulSoup(
                opinion_content, "html.parser"
            ).getText()
        cl_opinions.append(opinion_content)
    return cl_opinions


def map_and_merge_opinions(cluster: int, harvard_data: Dict[str, Any]) -> None:
    """Map and merge opinion data

    :param cluster: Cluster ID
    :param harvard_data: json data from harvard case
    :return: None
    """
    used_combined_opinions = False
    case_body = harvard_data["casebody"]["data"]
    sub_opinions = Opinion.objects.filter(cluster__id=cluster)

    soup = BeautifulSoup(case_body, "lxml")
    harvard_html = soup.find_all(
        lambda tag: (tag.name == "opinion" and tag.get("data-type") is None)
        or tag.get("data-type") == "opinion"
    )
    harvard_opinions = [op for op in harvard_html]
    cl_opinions = fetch_cl_opinion_content(sub_opinions=sub_opinions)

    if len(harvard_opinions) != len(cl_opinions):
        used_combined_opinions = True
    else:
        # crashes without a sub opinion ... that makes sense
        matches = match_lists(harvard_opinions, cl_opinions)
        if not matches:
            used_combined_opinions = True

        if not used_combined_opinions:
            for k, v in matches.items():
                op = sub_opinions[k]
                author_str = ""
                author = harvard_opinions[v].find("author")
                if author:
                    # Prettify the name a bit
                    author_str = titlecase(author.text.strip(":"))
                if op.author_str == "":
                    # We have an empty author name
                    if author_str:
                        # Store the name extracted from the author tag
                        op.author_str = author_str
                else:
                    if author_str:
                        if extract_judge_last_name(
                            op.author_str
                        ) != extract_judge_last_name(author_str):
                            # Raise an exception, check in the log for
                            # difference between author names
                            raise AuthorException(
                                "Authors don't match - log error"
                            )

                op.xml_harvard = str(harvard_opinions[v])
                op.save()

    if used_combined_opinions:
        # If we cant quite merge the opinions. Create combined opinion.
        # This occurs when the harvard data or CL data is slightly askew.
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
        parser.add_argument(
            "--fastcase",
            action="store_true",
            help="Fastcase flag",
        )

    def handle(self, *args, **options) -> None:
        if options["no_debug"]:
            logging.disable(logging.DEBUG)

        if options["cluster_id"] == None:
            sources_without_harvard = [
                source[0]
                for source in Docket.SOURCE_CHOICES
                if "Harvard" not in source[1]
            ]
            cluster_ids = (
                OpinionCluster.objects.filter(
                    docket__source__in=sources_without_harvard,
                    filepath_json_harvard__isnull=False,
                )
                .exclude(filepath_json_harvard__exact="")
                .values_list("id", "filepath_json_harvard", flat=False)
            )
            logger.info(msg=f"{len(cluster_ids)} left to merge")
        else:
            cluster_ids = OpinionCluster.objects.filter(
                id=options["cluster_id"]
            ).values_list("id", "filepath_json_harvard", flat=False)

        for cluster_id in cluster_ids:
            logger.info(msg=f"Merging {cluster_id[0]} at {cluster_id[1]}")
            merge_opinion_clusters(
                cluster_id=cluster_id[0], only_fastcase=options["fastcase"]
            )
