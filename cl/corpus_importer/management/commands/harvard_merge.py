import itertools
import json
import logging
from typing import Any

import requests
from bs4 import BeautifulSoup
from django.db import transaction
from juriscraper.lib.string_utils import titlecase

from cl.corpus_importer.management.commands.harvard_opinions import (
    parse_extra_fields,
    validate_dt,
)
from cl.corpus_importer.utils import (
    AuthorException,
    ClusterSourceException,
    DocketSourceException,
    EmptyOpinionException,
    JudgeException,
    OpinionMatchingException,
    OpinionTypeException,
    match_opinion_lists,
    merge_case_names,
    merge_docket_numbers,
    merge_overlapping_data,
)
from cl.lib.command_utils import VerboseCommand, logger
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


def find_data_fields(soup: BeautifulSoup, field_name: str) -> list:
    """Find field by tag name or data-type attribute

    :param soup: parsed document
    :param field_name: field to find
    :return: list of all fields found
    """
    return soup.find_all(
        lambda tag: (tag.name == field_name and tag.get("data-type") is None)
        or tag.get("data-type") == field_name
    )


def read_json(cluster: OpinionCluster) -> dict[str, Any] | None:
    """Helper method to read json into object

    :param cluster: the cluster to fetch the filepath for
    :return: Harvard data as a json object or None
    """

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


def get_data_source(harvard_data: dict[str, Any]) -> str:
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


def fetch_non_harvard_data(harvard_data: dict[str, Any]) -> dict[str, Any]:
    """Get data from harvard casebody and preprocess

    :param harvard_data:
    :return: dict with values extracted from casebody
    """
    soup = BeautifulSoup(harvard_data["casebody"]["data"], "lxml")

    judge_list = [
        find_all_judges(tag.text) for tag in find_data_fields(soup, "judges")
    ]

    # Convert list of lists to list and titlecase names
    judge_list = list(itertools.chain.from_iterable(judge_list))
    judge_list = list(map(titlecase, judge_list))

    author_list = [
        find_just_name(tag.text) for tag in find_data_fields(soup, "author")
    ]

    # titlecase names
    author_list = list(map(titlecase, author_list))

    # Flatten and dedupe list of judges
    judges = ", ".join(sorted(set(judge_list + author_list)))

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
        find_attorneys_fields = find_data_fields(soup, "attorneys")
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
    cluster: OpinionCluster, harvard_data: dict
) -> dict[str, tuple]:
    """Combine non overlapping data and return dictionary of data for merging

    :param cluster: Cluster to merge
    :param harvard_data: The harvard data as json
    :return: Optional dictionary of data to continue to merge
    """
    all_data = fetch_non_harvard_data(harvard_data)
    changed_values_dictionary: dict[str, tuple] = {}
    to_update: dict[str, Any] = {}
    for key, value in all_data.items():
        cl_value = getattr(cluster, key)
        if not cl_value:
            # Value is empty for key, we can add it directly to the object
            to_update[key] = value
        else:
            if value != cl_value:
                # We have different values, update dict
                changed_values_dictionary[key] = (value, cl_value)

    if to_update:
        # Update all fields at once
        OpinionCluster.objects.filter(id=cluster.id).update(**to_update)

    return changed_values_dictionary


def merge_cluster_dates(
    cluster: OpinionCluster,
    field_name: str,
    overlapping_data: tuple | None,
) -> dict[str, Any]:
    """Compare two dates and choose the best to update the opinion cluster
    the value if one value is better than the other

    :param cluster: Cluster to update
    :param field_name: field name to update in opinion cluster
    :param overlapping_data: data to compare
    :return: None
    """
    if not overlapping_data:
        return {}

    harvard_data, cl_date = overlapping_data
    if harvard_data:
        harvard_date, harvard_date_is_approximate = validate_dt(harvard_data)
        if cluster.docket.source == Docket.SCRAPER:
            # Give preference to harvard data
            if harvard_date != cl_date:
                return {field_name: harvard_date}
        elif (
            cluster.date_filed_is_approximate
            and not harvard_date_is_approximate
        ):
            # For some reason docket source is different, then check if
            # one date is approximate and the other is not if harvard
            # date is not approximate, it should be better
            return {field_name: harvard_date}

    return {}


def merge_date_filed(
    cluster: OpinionCluster, harvard_data: dict
) -> dict[str, Any]:
    """Merge date filed

    :param cluster: The cluster of the merging item
    :param harvard_data: json data from harvard case
    :return: None
    """

    harvard_date_filed = harvard_data.get("decision_date")
    cluster_date_filed = cluster.date_filed
    return merge_cluster_dates(
        cluster, "date_filed", (harvard_date_filed, cluster_date_filed)
    )


def update_docket_source(cluster: OpinionCluster) -> None:
    """Update docket source and complete

    :param cluster: the cluster object
    :return: None
    """
    docket = cluster.docket
    if docket.source in Docket.NON_HARVARD_SOURCES():
        # Add the Harvard source only if it has not been added before.
        new_docket_source = Docket.HARVARD + docket.source
        docket.source = new_docket_source
        docket.save()
    else:
        raise DocketSourceException("Unexpected docket source")


def update_cluster_source(cluster: OpinionCluster) -> None:
    """Update cluster source

    :param cluster: cluster object
    :return: None
    """
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


def save_headmatter(harvard_data: dict[str, Any]) -> dict[str, Any]:
    """Save and update headmatter

    Clean up the headmatter content - (pre opinion content) and save it

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

    return {"headmatter": "".join(headmatter)}


def merge_opinion_clusters(
    cluster_id: int,
    only_fastcase: bool = False,
    skip_judge_merger: bool = False,
) -> None:
    """Merge opinion cluster, docket and opinion data from Harvard

    :param cluster_id: The cluster ID to merger
    :param only_fastcase: Only process fastcase data
    :param skip_judge_merger: skip judge merger
    :return: None
    """
    opinion_cluster = OpinionCluster.objects.get(id=cluster_id)
    harvard_data = read_json(opinion_cluster)
    if not harvard_data:
        logger.warning(
            msg=f"No Harvard json for cluster: {opinion_cluster.id}"
        )
        return

    if only_fastcase and "Fastcase" != get_data_source(harvard_data):
        logger.info("Skipping non-fastcase opinion cluster")
        return

    try:
        with transaction.atomic():
            map_and_merge_opinions(opinion_cluster, harvard_data)

            changed_values_dictionary = combine_non_overlapping_data(
                opinion_cluster, harvard_data
            )

            # We need to reload the object because it was previously updated
            # in combine_non_overlapping_data
            opinion_cluster.refresh_from_db()

            updated_docket_number = merge_docket_numbers(
                opinion_cluster, harvard_data["docket_number"]
            )
            if updated_docket_number:
                opinion_cluster.docket.docket_number = updated_docket_number
                opinion_cluster.docket.save()

            case_names_to_update = merge_case_names(
                opinion_cluster,
                harvard_data,
                case_name_key="name_abbreviation",
                case_name_full_key="name",
            )
            date_filed_to_update = merge_date_filed(
                opinion_cluster, harvard_data
            )

            overlapping_data_long_fields = [
                "syllabus",
                "summary",
                "history",
                "headnotes",
                "correction",
                "cross_reference",
                "disposition",
                "arguments",
            ]
            overlapping_data_to_update = merge_overlapping_data(
                opinion_cluster,
                overlapping_data_long_fields,
                changed_values_dictionary,
                skip_judge_merger,
                is_columbia=False,
            )

            headmatter_data = save_headmatter(harvard_data)

            # Merge results
            data_to_update = (
                case_names_to_update
                | date_filed_to_update
                | overlapping_data_to_update
                | headmatter_data
            )

            if "other_dates" in changed_values_dictionary:
                data_to_update.update(
                    merge_cluster_dates(
                        opinion_cluster,
                        "other_dates",
                        changed_values_dictionary.get("other_dates"),
                    )
                )

            if data_to_update:
                OpinionCluster.objects.filter(id=cluster_id).update(
                    **data_to_update
                )

            # We need to refresh the object before trying to use it to
            # update the cluster source
            opinion_cluster.refresh_from_db()

            update_docket_source(opinion_cluster)
            update_cluster_source(opinion_cluster)
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
    except OpinionTypeException:
        logger.warning(
            msg=f"Opinion type not found in xml file for cluster id: {cluster_id}"
        )
    except EmptyOpinionException:
        logger.warning(
            msg=f"Opinion tag probably empty in json file from cluster id: {cluster_id}"
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
                if (
                    find_just_name(op.author_str).lower()
                    != find_just_name(author_str).lower()
                ):
                    raise AuthorException("Authors don't match")
                elif any(s.isupper() for s in op.author_str.split(",")):
                    # Some names are uppercase, update with processed names
                    op.author_str = author_str

        clean_opinion = fix_footnotes(harvard_opinions[int(k)])
        clean_opinion = fix_pagination(clean_opinion)
        op.xml_harvard = str(clean_opinion)
        op.save()


def map_and_merge_opinions(
    cluster: OpinionCluster, harvard_data: dict[str, Any]
) -> None:
    """Map and merge opinion data

    Map and merge opinions in clusters. If an opinion cluster has multiple
    opinions, we attempt to map the opinions to each other. In some
    cases - the style between Harvard and Columbia is different.
    In those cases we do not create new opinions and just rely on the data
    that we previously had and log that we did not create new opinions.

    :param cluster: Cluster object
    :param harvard_data: json data from harvard case
    :return: None
    """

    map_types = HarvardConversionUtil.types_mapping
    cl_opinions = Opinion.objects.filter(cluster__id=cluster.id)
    soup = BeautifulSoup(harvard_data["casebody"]["data"], "lxml")
    harvard_opinions = find_data_fields(soup, "opinion")

    if len(harvard_opinions) == len(cl_opinions):
        try:
            matches = match_opinion_lists(
                [op.getText() for op in harvard_opinions],
                fetch_cl_opinion_content(sub_opinions=cl_opinions),
            )
        except ZeroDivisionError:
            raise EmptyOpinionException(
                "Opinion tag probably empty in harvard data"
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
                    cluster_id=cluster.id,
                    type=opinion_type,
                    author_str=(
                        titlecase(find_just_name(author.text.strip(":")))
                        if author
                        else ""
                    ),
                )
            else:
                raise OpinionTypeException(
                    "Harvard opinion has no type "
                    f"attribute: {cluster.filepath_json_harvard}"
                )
    else:
        # Skip creating new opinion cluster due to differences between
        # Columbia and Harvard data set/parsing.
        logger.info(
            msg=f"Skip merging mismatched opinions on cluster: {cluster.id}"
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
            "--skip-judge-merger",
            action="store_true",
            help="Set flag to skip judge merger if the judges do not match",
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
            else:
                logger.info(
                    f"Cluster ID: {options['cluster_id']} doesn't exist"
                )

        for cluster_id, filepath in cluster_ids:
            logger.info(msg=f"Merging {cluster_id} at {filepath}")
            merge_opinion_clusters(
                cluster_id=cluster_id,
                only_fastcase=options["fastcase"],
                skip_judge_merger=options["skip_judge_merger"],
            )
