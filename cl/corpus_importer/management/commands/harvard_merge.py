import itertools
import json
import logging
from datetime import date
from typing import Any, Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag
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

        # We check if any word in the string is uppercase
        cl_data_upper = (
            True if [s for s in cl_data.split(",") if s.isupper()] else False
        )

        # Get last names keeping case and cleaning the string (We could have
        # the judge names in capital letters)
        cl_clean = set(
            extract_judge_last_name(cl_data, keep_letter_case=cl_data_upper)
        )
        # Get last names in lowercase and cleaned
        harvard_clean = set(extract_judge_last_name(harvard_data))
        judges = titlecase(", ".join(extract_judge_last_name(harvard_data)))

        if (
            harvard_clean.issuperset(cl_clean) or cl_data_upper
        ) and harvard_clean != cl_clean:
            OpinionCluster.objects.filter(id=cluster_id).update(judges=judges)
        elif not harvard_clean.intersection(
            set(extract_judge_last_name(cl_data))
        ):
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
    :param changed_values_dictionary: the dictionary of data to merge
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


def save_headmatter(cluster_id: int, harvard_data: Dict[str, Any]) -> None:
    """Save and update headmatter

    Clean up the headmatter content - (pre opinion content) and save it

    :param cluster_id: Cluster ID
    :param harvard_data: json data from harvard case
    :return: None
    """
    case_body = harvard_data["casebody"]["data"]
    soup = BeautifulSoup(case_body, "lxml")
    soup = fix_pagination(soup)

    content = list(soup.find("opinion").previous_siblings)[::-1]
    headmatter = []
    for item in content:
        if item == "\n":
            continue
        if 'id="b' in str(item) and len(headmatter) > 0:
            item = f"<br>{str(item)}"
        else:
            item = str(item)
        headmatter.append(str(item))
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
    if harvard_data:
        if only_fastcase:
            source = get_data_source(harvard_data)
            if source == "Fastcase":
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
            logger.warning(msg=f"Author Exception for cluster {cluster_id}")
        except JudgeException:
            logger.warning(msg=f"Judge Exception for: {cluster_id}")
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


def fix_pagination(soup: BeautifulSoup) -> BeautifulSoup:
    """Add pagination to harvard XML

    Add star pagination to page number XML/HTML
    :param soup: The content to cleanup
    :return: soup
    """
    for pgnmbr in soup.find_all("page-number"):
        pgnmbr.name = "span"
        pgnmbr["class"] = "star-pagination"
        pgnmbr.string = f" {pgnmbr.string} "
    return soup


def fix_footnotes(soup: BeautifulSoup) -> BeautifulSoup:
    """Fix footnotes

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

    # Append the footnotes_div to the main 'opinion' element
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
            author_str = titlecase(
                ", ".join(extract_judge_last_name(author.text.strip(":")))
            )
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
                    raise AuthorException(f"Authors don't match - log error")
                else:
                    # The names are the same when processed, just make sure
                    # the cl data is not all uppercase or part of it
                    cl_author_data_upper = (
                        True
                        if [s for s in op.author_str.split(",") if s.isupper()]
                        else False
                    )

                    if cl_author_data_upper:
                        # Some names are uppercase, update with processed names
                        op.author_str = author_str

        clean_opinion = fix_footnotes(harvard_opinions[int(k)])
        clean_opinion = fix_pagination(clean_opinion)
        op.xml_harvard = str(clean_opinion)
        op.save()


def create_opinion(harvard_html: Tag, opinion_type: str, cluster: int) -> None:
    """Create a new opinion
    :param harvard_html: BS element that contains opinion
    :param opinion_type: opinion type from Opinion model
    :param cluster: id from opinion cluster
    :return: None
    """

    author_str = ""
    author = harvard_html.find("author")
    if author:
        # Prettify the name a bit
        author_str = titlecase(author.text.strip(":"))

    Opinion.objects.create(
        xml_harvard=str(harvard_html),
        cluster=OpinionCluster.objects.get(id=cluster),
        type=opinion_type,
        author_str=author_str,
    )


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

    if len(harvard_html) != len(sub_opinions):
        specific_sub_opinions = sub_opinions.exclude(type="010combined")
        if specific_sub_opinions.count() == 0:
            # Our only opinion is a combined opinion
            for op in harvard_html:
                if op.has_attr("type"):
                    opinion_type = types_mapping.get(op.get("type"))
                    if opinion_type:
                        create_opinion(op, opinion_type, cluster)
                    else:
                        raise OpinionTypeException(
                            f"Opinion type unknown: {op.get('type')}"
                        )
                else:
                    # It cannot create opinion, it has no type
                    raise OpinionTypeException(
                        f"Opinion from json file in cluster_id: {cluster} has no type"
                    )
        else:
            # Try to match cluster sub opinions with json opinions
            harvard_opinions = [op for op in harvard_html]
            specific_sub_opinions = sub_opinions.exclude(type="010combined")
            cl_opinions = fetch_cl_opinion_content(
                sub_opinions=specific_sub_opinions
            )
            matches = match_lists(harvard_opinions, cl_opinions)
            if matches:
                # Update matching opinions
                update_matching_opinions(
                    matches, specific_sub_opinions, harvard_opinions
                )
            else:
                # We have opinions but for some unknown reason they don't match
                logger.warning(
                    msg=f"Opinions don't match with json file on cluster id: {cluster}"
                )

    else:
        # Cl opinions and harvard opinions have the same length, try to match
        # opinions
        harvard_opinions = [op for op in harvard_html]
        cl_opinions = fetch_cl_opinion_content(sub_opinions=sub_opinions)
        matches = match_lists(harvard_opinions, cl_opinions)
        if not matches:
            used_combined_opinions = True

        if not used_combined_opinions:
            # Update matching opinions
            update_matching_opinions(matches, sub_opinions, harvard_opinions)

    if used_combined_opinions:
        combined_opinions = sub_opinions.filter(type="010combined")

        if combined_opinions:
            if combined_opinions.count() == 1:
                # Try to match old and new combined opinion
                cl_combined_opinion = fetch_cl_opinion_content(
                    sub_opinions=combined_opinions
                )
                harvard_combined_opinion = [
                    "\n".join([str(op) for op in harvard_html])
                ]
                matches = match_lists(
                    harvard_combined_opinion, cl_combined_opinion
                )
                if matches:
                    # Update combined opinion
                    update_matching_opinions(
                        matches, cl_combined_opinion, harvard_combined_opinion
                    )

            else:
                # We have more than one combined opinion
                logger.warning(
                    msg=f"Cluster id: {cluster} has more than one "
                    f"combined opinion. Can't update combined"
                    f" opinion."
                )
        else:
            # We don't have a combined opinion, create combined opinion
            Opinion.objects.create(
                xml_harvard="\n".join([str(op) for op in harvard_html]),
                cluster=OpinionCluster.objects.get(id=cluster),
                type="010combined",
            )
            logger.info(
                msg=f"Combined opinion created in cluster id: {cluster}"
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
        parser.add_argument(
            "--start-after", type=int, required=False, help="1261102"
        )
        parser.add_argument(
            "--quantity",
            type=int,
            default=10000,
            help="How many mergers to run at one time",
        )

    def handle(self, *args, **options) -> None:
        if options["no_debug"]:
            logging.disable(logging.DEBUG)

        if options["cluster_id"] is None:
            cluster_ids = (
                OpinionCluster.objects.exclude(filepath_json_harvard="")
                .exclude(source__contains="U")
                .values_list("id", "filepath_json_harvard")
            )[: options["quantity"]]
            if options["start_after"]:
                index = [x[0] for x in cluster_ids].index(
                    options["start_after"]
                )
                if index:
                    cluster_ids = cluster_ids[index + 1 :]

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
