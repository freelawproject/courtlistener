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
from cl.people_db.lookup_utils import find_all_judges, find_just_name
from cl.search.models import SOURCES, Docket, Opinion, OpinionCluster


class HarvardConversionUtil:
    types_mapping = {
        "unanimous": "015unamimous",
        "majority": "020lead",
        "plurality": "025plurality",
        "concurrence": "030concurrence",
        "concurring-in-part-and-dissenting-in-part": "035concurrenceinpart",
        "dissent": "040dissent",
        "remittitur": "060remittitur",
        "rehearing": "070rehearing",
        "on-the-merits": "080onthemerits",
        "on-motion-to-strike-cost-bill": "090onmotiontostrike",
    }


class AuthorException(Exception):
    """Error found in author merger."""

    def __init__(self, message: str) -> None:
        self.message = message


class JudgeException(Exception):
    """An exception for wrong judges"""

    def __init__(self, message: str) -> None:
        self.message = message


class OpinionMatchingException(Exception):
    """An exception for wrong matching opinions"""

    def __init__(self, message: str) -> None:
        self.message = message


class DocketSourceException(Exception):
    """An exception for wrong docket source"""

    def __init__(self, message: str) -> None:
        self.message = message


class ClusterSourceException(Exception):
    """An exception for wrong cluster source"""

    def __init__(self, message: str) -> None:
        self.message = message


class OpinionTypeException(Exception):
    """An exception for incorrect opinion types"""

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

    judge_list = [
        find_all_judges(tag.text)
        for tag in soup.find_all(
            lambda tag: (tag.name == "judges" and tag.get("data-type") is None)
            or tag.get("data-type") == "judges"
        )
    ]

    # Convert list of lists to list and titlecase names
    judge_list = list(itertools.chain.from_iterable(judge_list))
    judge_list = list(map(titlecase, judge_list))

    author_list = [
        find_just_name(tag.text)
        for tag in soup.find_all(
            lambda tag: (tag.name == "author" and tag.get("data-type") is None)
            or tag.get("data-type") == "author"
        )
    ]

    # titlecase names
    author_list = list(map(titlecase, author_list))

    # Flatten and dedupe list of judges
    judges = ", ".join(sorted(list(set(judge_list + author_list))))

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

    # Find any legal field
    find_any_legal_field = soup.find(
        lambda tag: tag.get("data-type") == "legal"
    )

    if find_any_legal_field:
        # We have legal field, then collect all legal and attorneys fields
        find_fields = soup.find_all(
            lambda tag: tag.get("data-type") == "legal"
            or (tag.name == "attorneys" and tag.get("data-type") is None)
            or tag.get("data-type") == "attorneys"
        )
        if find_fields:
            # Combine attorneys and legal data-type fields
            arguments = " ".join(str(x) for x in find_fields)
            all_data["arguments"] = arguments
    else:
        # Only save attorneys
        find_attorneys_fields = soup.find_all(
            lambda tag: tag.get("data-type") == "attorneys"
            or (tag.name == "attorneys" and tag.get("data-type") is None)
        )
        if find_attorneys_fields:
            attorneys = " ".join(str(x) for x in find_attorneys_fields)
            all_data["attorneys"] = attorneys

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

        # We check if any word in the string is uppercase
        cl_data_upper = (
            True if [s for s in cl_data.split(",") if s.isupper()] else False
        )

        # Get last names keeping case and cleaning the string (We could have
        # the judge names in capital letters)
        cl_clean = set(find_all_judges(cl_data))
        # Get last names in lowercase and cleaned
        harvard_clean = set(find_all_judges(harvard_data))
        judges = titlecase(", ".join(find_all_judges(harvard_data)))

        if (
            harvard_clean.issuperset(cl_clean) or cl_data_upper
        ) and harvard_clean != cl_clean:
            OpinionCluster.objects.filter(id=cluster_id).update(judges=judges)
        elif not harvard_clean.intersection(set(find_all_judges(cl_data))):
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
                # For some reason docket source is different, then check if
                # one date is approximate and the other is not if harvard
                # date is not approximate, it should be better
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
    cl_docket = OpinionCluster.objects.get(id=cluster_id).docket

    if cl_docket.docket_number:
        # Check if docket number exists
        # e.g. CL docket id #3952066 doesn't have
        cl_clean_docket = clean_docket_number(cl_docket.docket_number)
        h_clean_docket = clean_docket_number(harvard_docket_number)

        if (
            cl_clean_docket in h_clean_docket
            and cl_docket.docket_number != h_clean_docket
        ):
            cl_docket.docket_number = h_clean_docket
            cl_docket.save()
        else:
            # Check if their relatively similar and if so save the harvard one
            # if its longer
            similarity = get_cosine_similarity(cl_clean_docket, h_clean_docket)
            if similarity > 0.8:
                if len(h_clean_docket) > len(cl_clean_docket):
                    cl_docket.docket_number = h_clean_docket
                    cl_docket.save()


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
    :param changed_values_dictionary: the dictionary of data to merge
    :return: None
    """

    if not changed_values_dictionary:
        # Empty dictionary means that we don't have overlapping data
        return

    long_fields = [
        "syllabus",
        "summary",
        "history",
        "headnotes",
        "correction",
        "cross_reference",
        "disposition",
        "arguments",
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
    new_docket_source = Docket.HARVARD + docket.source
    if new_docket_source in [
        Docket.HARVARD,
        Docket.HARVARD_AND_RECAP,
        Docket.SCRAPER_AND_HARVARD,
        Docket.HARVARD_AND_COLUMBIA,
        Docket.DIRECT_INPUT_AND_HARVARD,
        Docket.ANON_2020_AND_HARVARD,
        Docket.ANON_2020_AND_SCRAPER_AND_HARVARD,
    ]:
        # Source is limited to those options because those are the only
        # valid options when we sum the source with harvard source
        docket.source = new_docket_source
        docket.save()
    else:
        raise DocketSourceException("Unexpected docket source")


def update_cluster_source(cluster_id: int) -> None:
    """Update cluster source

    :param cluster_id: cluster id to update
    :return: None
    """
    cluster = OpinionCluster.objects.get(id=cluster_id)
    new_cluster_source = cluster.source + SOURCES.HARVARD_CASELAW

    if new_cluster_source in [
        SOURCES.COURT_M_HARVARD,
        SOURCES.ANON_2020_M_HARVARD,
        SOURCES.COURT_M_RESOURCE_M_HARVARD,
        SOURCES.DIRECT_COURT_INPUT_M_HARVARD,
        SOURCES.LAWBOX_M_HARVARD,
        SOURCES.LAWBOX_M_COURT_M_HARVARD,
        SOURCES.LAWBOX_M_RESOURCE_M_HARVARD,
        SOURCES.LAWBOX_M_COURT_RESOURCE_M_HARVARD,
        SOURCES.MANUAL_INPUT_M_HARVARD,
        SOURCES.PUBLIC_RESOURCE_M_HARVARD,
        SOURCES.COLUMBIA_ARCHIVE_M_HARVARD,
    ]:
        cluster.source = new_cluster_source
        cluster.save()
    else:
        raise ClusterSourceException("Unexpected cluster source")


def save_headmatter(cluster_id: int, harvard_data: Dict[str, Any]) -> None:
    """Save and update headmatter

    Clean up the headmatter content - (pre opinion content) and save it

    :param cluster_id: Cluster ID
    :param harvard_data: json data from harvard case
    :return: None
    """
    soup = BeautifulSoup(harvard_data["casebody"]["data"], "lxml")
    for op in soup.find_all("opinion"):
        op.decompose()
    headmatter = []
    soup = fix_footnotes(soup)
    index = 0
    for element in soup.find("casebody").find_all(recursive=False):
        element = fix_pagination(element)
        if element.get("id", "").startswith("b") and index > 0:
            headmatter.append(f"<br>{str(element)}")
        else:
            headmatter.append(str(element))
        index += 1
    OpinionCluster.objects.filter(id=cluster_id).update(
        headmatter="".join(headmatter)
    )


def merge_opinion_clusters(
    cluster_id: int, only_fastcase: bool = False
) -> None:
    """Merge opinion cluster, docket and opinion data from Harvard

    :param cluster_id: The cluster ID to merger
    :param only_fastcase: Only process fastcase data
    :return: None
    """
    harvard_data = read_json(cluster_id)
    if not harvard_data:
        logger.warning(msg=f"No Harvard json for cluster: {cluster_id}")
        return

    if only_fastcase and "Fastcase" != get_data_source(harvard_data):
        logger.info("Skipping non-fastcase opinion cluster")
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
            save_headmatter(cluster_id, harvard_data)
            update_docket_source(cluster_id=cluster_id)
            update_cluster_source(cluster_id=cluster_id)
            logger.info(msg=f"Finished merging cluster: {cluster_id}")

    except AuthorException:
        logger.warning(msg=f"Author exception for cluster id: {cluster_id}")
    except JudgeException:
        logger.warning(msg=f"Judge exception for cluster id: {cluster_id}")
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


def fix_pagination(soup: BeautifulSoup) -> BeautifulSoup:
    """Add pagination to harvard XML

    Add star pagination to page number XML/HTML
    :param soup: The content to clean up
    :return: soup
    """
    for pgnmbr in soup.find_all("page-number"):
        pgnmbr.name = "span"
        pgnmbr["class"] = "star-pagination"
        pgnmbr.string = f" {pgnmbr.string} "
    return soup


def fix_footnotes(soup: BeautifulSoup) -> BeautifulSoup:
    """Make Footnotes work with CL

    Enable footnote linking between footnotes and footnotemark

    :param soup: Bs4 object to clean up
    :return:Content with working footnotes
    """
    for fn in soup.find_all("footnotemark"):
        fn.name = "a"
        fn["href"] = f"#fn{fn.string}"
        fn["id"] = f"fn{fn.string}_ref"
        fn["class"] = "footnote"

        fnl = soup.find("footnote", {"label": fn.string})
        if fnl:
            obj = f'<a class="footnote" href="#fn{fn.string}_ref">{fn.string}</a>'
            fnl.name = "div"
            fnl["class"] = "footnote"
            fnl["id"] = f"fn{fn.string}"
            sp2 = BeautifulSoup(obj, "html.parser")
            fnl.insert(0, sp2)

    soup = BeautifulSoup(str(soup.prettify()), "xml")
    footnotes_div = soup.new_tag("div", attrs={"class": "footnotes"})

    # Find all div elements with the class 'footnote'
    footnote_divs = soup.find_all("div", class_="footnote")
    if not footnote_divs:
        return soup

    # Wrap each footnote div with the footnotes_div
    for div in footnote_divs:
        footnotes_div.append(div.extract())

    # Append the footnotes_div to the main 'opinion' element or headmatter
    if not soup.find("opinion"):
        soup.find("casebody").append(footnotes_div)
    else:
        opinion = soup.find("opinion")
        opinion.append(footnotes_div)
    return soup


def update_matching_opinions(
    matches: dict, cluster_sub_opinions: list, harvard_opinions: list
) -> None:
    """Update matching opinions

    :param matches: dict with matching position from queryset and harvard opinions
    :param cluster_sub_opinions: queryset of opinions
    :param harvard_opinions: list of harvard opinions
    :return: None
    """
    for k, v in matches.items():
        op = cluster_sub_opinions[int(v)]
        author_str = ""
        author = harvard_opinions[int(k)].find("author")
        if author:
            # Prettify the name a bit
            author_str = titlecase(find_just_name(author.text.strip(":")))
        if op.author_str == "":
            # We have an empty author name
            if author_str:
                # Store the name extracted from the author tag
                op.author_str = author_str
        else:
            if author_str:
                if find_just_name(op.author_str) != find_just_name(author_str):
                    raise AuthorException(f"Authors don't match - log error")
                elif any(s.isupper() for s in op.author_str.split(",")):
                    # Some names are uppercase, update with processed names
                    op.author_str = author_str

        clean_opinion = fix_footnotes(harvard_opinions[int(k)])
        clean_opinion = fix_pagination(clean_opinion)
        op.xml_harvard = str(clean_opinion)
        op.save()


def map_and_merge_opinions(cluster: int, harvard_data: Dict[str, Any]) -> None:
    """Map and merge opinion data

    :param cluster: Cluster ID
    :param harvard_data: json data from harvard case
    :return: None
    """

    map_types = HarvardConversionUtil.types_mapping
    cl_opinions = Opinion.objects.filter(cluster__id=cluster)
    soup = BeautifulSoup(harvard_data["casebody"]["data"], "lxml")
    harvard_opinions = soup.find_all(
        lambda tag: (tag.name == "opinion" and tag.get("data-type") is None)
        or tag.get("data-type") == "opinion"
    )

    if len(harvard_opinions) == len(cl_opinions):
        matches = match_lists(
            [op for op in harvard_opinions],
            fetch_cl_opinion_content(sub_opinions=cl_opinions),
        )
        if len(matches) == len(harvard_opinions):
            update_matching_opinions(matches, cl_opinions, harvard_opinions)
        else:
            raise OpinionMatchingException("Failed to match opinions")

    elif len(harvard_opinions) > len(cl_opinions) and len(cl_opinions) == 1:
        for op in harvard_opinions:
            if op.has_attr("type"):
                opinion_type = map_types.get(op.get("type"))
                if not opinion_type:
                    raise OpinionTypeException(
                        f"Opinion type unknown: {op.get('type')}"
                    )
                author = op.find("author")

                Opinion.objects.create(
                    xml_harvard=str(op),
                    cluster=OpinionCluster.objects.get(id=cluster),
                    type=opinion_type,
                    author_str=titlecase(
                        find_just_name(author.text.strip(":"))
                    )
                    if author
                    else "",
                )


class Command(VerboseCommand):
    help = "Merge harvard opinions into CL opinions"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--cluster-id",
            type=str,
            help="An individual cluster ID to merge",
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
            help="A flag to choose to merge only fastcase opinions",
        )
        parser.add_argument(
            "--offset",
            type=int,
            required=False,
            help="Offset the starting query by some ID",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10000,
            help="How many mergers to run at one time",
        )

    def handle(self, *args, **options) -> None:
        if options["no_debug"]:
            logging.disable(logging.DEBUG)

        if options["cluster_id"] is None:
            if options["offset"]:
                cluster_ids = (
                    OpinionCluster.objects.exclude(filepath_json_harvard="")
                    .filter(id__gt=options["offset"])
                    .order_by("id")
                    .exclude(source__contains=SOURCES.HARVARD_CASELAW)
                    .values_list("id", "filepath_json_harvard")
                )
            else:
                cluster_ids = (
                    OpinionCluster.objects.exclude(filepath_json_harvard="")
                    .order_by("id")
                    .exclude(source__contains=SOURCES.HARVARD_CASELAW)
                    .values_list("id", "filepath_json_harvard")
                )
            if options["limit"]:
                cluster_ids = cluster_ids[: options["limit"]]

            logger.info(msg=f"{len(cluster_ids)} left to merge")
        else:
            cluster_ids = (
                OpinionCluster.objects.filter(id=options["cluster_id"])
                .order_by("id")
                .values_list("id", "filepath_json_harvard", flat=False)
            )

            if cluster_ids:
                if (
                    SOURCES.HARVARD_CASELAW
                    in OpinionCluster.objects.get(id=cluster_ids[0][0]).source
                ):
                    logger.info(
                        f"Cluster id: {cluster_ids[0][0]} already merged."
                    )
                    return

        for cluster_id, filepath in cluster_ids:
            logger.info(msg=f"Merging {cluster_id} at {filepath}")
            merge_opinion_clusters(
                cluster_id=cluster_id, only_fastcase=options["fastcase"]
            )
