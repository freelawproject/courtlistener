import itertools
import re
from datetime import date, datetime
from typing import List, Optional, Union

import numpy as np
import pandas as pd
from courts_db import find_court
from django.db import IntegrityError, transaction
from django.db.models.query import QuerySet
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from juriscraper.lib.string_utils import CaseNameTweaker, harmonize
from pandas import DataFrame
from pandas.io.parsers import TextFileReader

from cl.citations.utils import map_reporter_db_cite_type
from cl.corpus_importer.utils import winnow_case_name
from cl.lib.command_utils import logger
from cl.search.models import Citation, Court, Docket, Opinion, OpinionCluster

cnt = CaseNameTweaker()


def load_citations_file(csv_path: str) -> DataFrame | TextFileReader:
    """Load csv file from absolute path

    :param csv_path: csv path
    :return: loaded data
    """

    data = pd.read_csv(csv_path, delimiter=",")
    # Replace nan in dataframe
    data = data.replace(np.nan, "", regex=True)
    logger.info(f"Found {len(data.index)} rows in csv file: {csv_path}")
    return data


def prepare_citation(citation: str) -> Union[List[FullCaseCitation], list]:
    """Convert str citation to valid citation objects

    :param citation: citation str
    :return: list of valid cites
    """
    clean_cite = re.sub(r"\s+", " ", citation)
    citations = get_citations(clean_cite)

    # There are some unsupported volume numbers in citations like "90-1 U.S.Tax Cas.
    # (CCH) P60,005". Volume field is defined as SmallIntegerField.
    citations = [
        cite
        for cite in citations
        if isinstance(cite, FullCaseCitation)
        and cite.groups.get("volume")
        and cite.groups.get("volume").isdigit()
    ]
    return citations


def case_names_overlap(case: OpinionCluster, case_name: str) -> bool:
    """Case names not overlap

    Check if the case names have quality overlapping case name words.
    Excludes 'bad words' and other common words
    :param case: The case opinion cluster
    :param case_name: The case name from csv
    :return: True if there is an overlap
    """

    # We combine as much data as possible for the case name to increase our
    # chances of getting a match
    cl_case_name = (
        f"{case.case_name} {case.case_name_short} {case.case_name_full}"
    )

    overlap = winnow_case_name(cl_case_name) & winnow_case_name(case_name)

    if overlap:
        return True
    return False


def prepare_date(date_str: Optional[str] = None) -> Optional[date]:
    """Convert dates like 'February 28, 2011', '2011-02-28' or '13-Jun-01' to date
    object

    :param date_str: date string
    :return: date object or None
    """
    if date_str:
        valid_formats = ["%B %d, %Y", "%Y-%m-%d", "%d-%b-%y"]
        for date_format in valid_formats:
            try:
                date_obj = datetime.strptime(date_str, date_format)
                return date_obj.date()
            except ValueError:
                continue
        logger.warning(f"Invalid date string: {date_str}")
    return None


def add_citations(
    citations: list, cluster_id: int, debug: bool = False
) -> None:
    """Add citation to OpinionCluster

    :param citations: list with valid citations
    :param cluster_id: Cluster id of found case
    :param debug: set false to save changes
    :return: None
    """

    for citation in citations:
        if Citation.objects.filter(
            cluster_id=cluster_id, reporter=citation.corrected_reporter()
        ).exists():
            # Avoid adding a citation if we already have a citation from the
            # citation's reporter
            continue

        # Get correct reporter type before trying to add the citation
        if not citation.corrected_reporter():
            reporter_type = Citation.STATE
        else:
            cite_type_str = citation.all_editions[0].reporter.cite_type
            reporter_type = map_reporter_db_cite_type(cite_type_str)

        try:
            if not debug:
                obj, created = Citation.objects.get_or_create(
                    volume=citation.groups["volume"],
                    reporter=citation.corrected_reporter(),
                    page=citation.groups["page"],
                    type=reporter_type,
                    cluster_id=cluster_id,
                )
            else:
                # Force to show log message when debug is true, if false log
                # message will only show if new citation is created
                created = True

            if created:
                logger.info(
                    f'Citation "{citation.corrected_citation()}"'
                    f" added to cluster id: {cluster_id}"
                )

        except IntegrityError:
            logger.warning(
                f"Reporter mismatch for cluster: {cluster_id} on "
                f"cite: {citation.corrected_citation()}"
            )


def get_court_filter(court: Optional[str] = None) -> dict:
    """Create dict with court filter

    :param court: court name or none
    :return: dict with court data or empty dict
    """
    if court:
        # Remove dot at end, court-db fails to find court with
        # dot at end, e.g. "Supreme Court of Pennsylvania." fails,
        # but "Supreme Court of Pennsylvania" doesn't
        court = court.strip(".")

        # Try without bankruptcy flag
        found_court = find_court(court, bankruptcy=False)

        if not found_court:
            # Try with bankruptcy flag
            found_court = find_court(court, bankruptcy=True)

        if len(found_court) >= 1:
            court_id = found_court[0]
            return {"docket__court__id": court_id}

    return {}


def add_stub_case(
    valid_citations: list,
    court_str: str,
    case_name: str,
    date_filed: Optional[str] = None,
    date_decided: Optional[str] = None,
    debug: bool = False,
) -> None:
    """Add stub case

    :param valid_citations: List of valid citations to add
    :param court_str: Court name
    :param case_name: Case name
    :param date_filed: Date filed optional
    :param date_decided: Date decided optional
    :param debug: if true don't save changes
    :return: None
    """

    # Remove dot at end
    court_name = court_str.strip(".")

    # Try without bankruptcy flag
    found_court = find_court(court_name, bankruptcy=False)

    if not found_court:
        # Try with bankruptcy flag
        found_court = find_court(court_name, bankruptcy=True)

    if len(found_court) >= 1:
        try:
            court = Court.objects.get(pk=found_court[0])
        except Court.DoesNotExist:
            logger.info(f"Court doesn't exist in database: {found_court[0]}")
            return
    else:
        logger.info(f"Couldn't find court: {court_name}")
        return

    # Prepare dates
    prep_date_filed = prepare_date(date_filed)
    prep_date_decided = prepare_date(date_decided)

    if court and (prep_date_filed or prep_date_decided):
        if not debug:
            with transaction.atomic():
                # Prepare case name
                case_name = harmonize(case_name)

                if case_name == "v.":
                    # Case name reduced to blank: "Plaintiff v. Defendant",
                    # this happened in row 2417 of file
                    # 20190510_minimal_metadata_bankruptcy.csv
                    logger.info(
                        f"Case name reduced to blank, can't add stub case."
                    )
                    return

                case_name_short = cnt.make_case_name_short(case_name)

                # TODO change with cluster stub model
                # TODO point citations to cluster stub object
                docket = Docket.objects.create(
                    source=0,
                    court=court,
                    case_name=case_name,
                    case_name_short=case_name_short,
                    case_name_full=case_name,
                    date_filed=prep_date_filed,
                )

                cluster = OpinionCluster.objects.create(
                    case_name=case_name,
                    case_name_short=case_name_short,
                    case_name_full=case_name,
                    docket=docket,
                    date_filed=prep_date_filed or prep_date_decided,
                    precedential_status="Unknown",
                )

                Opinion.objects.create(
                    cluster=cluster,
                    type="Lead Opinion",
                    plain_text="We don't have enough information about this "
                    "case/citation.",
                )

                add_citations(valid_citations, cluster.pk, debug)

                logger.info(
                    f"Added stub case correctly, cluster id: {cluster.pk}"
                )

        else:
            logger.info(f"Added stub case correctly")


def dict_all_combinations(d: dict, dates_filed: Optional[list] = None) -> list:
    """Generate all possible combinations of a dict

    :param d: dict with filters
    :param dates_filed: list with date_filed string dates
    :return: list of possible combinations of dict keys and values
    """
    results = []
    if dates_filed:
        for date_filed in dates_filed:
            d_copy = d.copy()
            d_copy["date_filed"] = date_filed
            # Generate filters with all date_filed possibilities
            for i in range(1, len(d_copy) + 1):
                results.extend(
                    list(map(dict, itertools.combinations(d_copy.items(), i)))
                )
    else:
        # We don't have any date_filed, generate filters
        for i in range(1, len(d) + 1):
            results.extend(
                list(map(dict, itertools.combinations(d.items(), i)))
            )

    # We remove possible duplicated filters generated when we have multiple
    # date_filed dates
    return [dict(t) for t in {tuple(d.items()) for d in results}]


def get_date_filter(
    date_filed: Optional[str] = None, date_decided: Optional[str] = None
) -> list:
    """Prepare dates to be used as filters

    :param date_filed: date filed
    :param date_decided: date decided
    :return: list with valid dates
    """
    # Store all possible date_filed dates
    dates_filed = []

    prep_date_filed = prepare_date(date_filed)
    if prep_date_filed:
        # Only add date if we have one
        dates_filed.append(prep_date_filed.strftime("%Y-%m-%d"))

    # Lexis dataset contains can contain the date_filed in date_decided
    # column, I found out this after taking a sample from dataset and
    # comparing it with courtlistener data
    prep_date_filed = prepare_date(date_decided)
    if prep_date_filed:
        dates_filed.append(prep_date_filed.strftime("%Y-%m-%d"))

    # We remove duplicates if date_filed is the same as date_decided
    dates_filed = list(set(dates_filed))

    return dates_filed


def find_cases_with_metadata(
    valid_citations: list,
    court: Optional[str] = None,
    date_filed: Optional[str] = None,
    date_decided: Optional[str] = None,
    case_name: Optional[str] = None,
    docket_number: Optional[str] = None,
) -> "QuerySet[OpinionCluster]":
    """Search for possible case using citation, court, date filed and case name

    :param valid_citations: list with valid citations from csv row
    :param court: Court name
    :param date_filed: The date the case was filed
    :param date_decided: The date the case was decided, in cl is also the date
    the case was filed
    :param case_name: The case name
    :param docket_number: The docket number
    :return: OpinionCluster QuerySet
    """

    results_ids = []
    for citation in valid_citations:
        # Lexis data contains many citations, we need to find at least one
        # case with the citation, so we can add the others

        citation_search_params = {
            "citations__volume": citation.groups.get("volume"),
            "citations__reporter": citation.corrected_reporter(),
            "citations__page": citation.groups.get("page"),
        }

        # Filter by citation
        cluster_results = OpinionCluster.objects.filter(
            **citation_search_params
        )

        # Store the count to use it in the following code
        results_count = cluster_results.count()
        if results_count == 1:
            if case_name:
                names_are_similar = case_names_overlap(
                    cluster_results.first(), case_name
                )
                if names_are_similar:
                    # Case names are similar, we have a match, store the pk
                    results_ids.append(cluster_results.first().pk)

        if not results_ids:
            # If we don't get a single match with citation

            # Basic filter
            filters = {"case_name": case_name}

            if docket_number:
                filters["docket__docket_number"] = docket_number

            # Add court to filters if we have court in csv
            filters.update(get_court_filter(court))

            dates_filed = get_date_filter(date_filed, date_decided)

            # Remove any None value
            filters = {
                key: value
                for key, value in filters.items()
                if value is not None
            }

            # Generate all possible combinations of filters
            generated_filters = dict_all_combinations(filters, dates_filed)
            # We start with complex filters and go to most basic filter which
            # can return multiple results
            generated_filters = sorted(
                generated_filters, key=lambda d: len(d.keys()), reverse=True
            )

            # Apply all possible combination of filters to try to get the case
            for queryset_filter in generated_filters:
                # cluster_results is already filtered by citation
                if cluster_results:
                    # When we have results with citation
                    results = cluster_results.filter(**queryset_filter)
                else:
                    # When we don't have any results with citation, use the
                    # other filters to try to find the case
                    results = OpinionCluster.objects.filter(**queryset_filter)
                filter_results_count = results.count()
                if filter_results_count == 1:
                    if case_name:
                        names_are_similar = case_names_overlap(
                            results.first(), case_name
                        )
                        if names_are_similar:
                            # We found a case with similar name to lexis data,
                            # store pk
                            results_ids.append(results.first().pk)
                else:
                    # Try next filter
                    continue

            if not results_ids:
                # We couldn't find a match using filters, if only filtering by
                # citation gave us a large queryset, lets try to compare each
                # result with case name to try to find a match
                if results_count > 1:
                    for cluster in cluster_results:
                        if case_name:
                            names_are_similar = case_names_overlap(
                                cluster, case_name
                            )
                            if names_are_similar:
                                # We found a case with similar name to lexis
                                # data
                                results_ids.append(cluster.pk)

    # Remove possible duplicated ids
    results_ids = list(set(results_ids))

    if len(results_ids) > 1:
        # Possible duplicate cases, we return all objects, but we will skip that row
        # because the citations could be added to the wrong case
        logger.warning(
            f"Possible duplicated cases with ids: {','.join(map(str, results_ids))}"
        )

    # Return a queryset of all the possible cases matched by filter and case
    # name overlap, remove duplicated ids to filter
    return OpinionCluster.objects.filter(pk__in=results_ids)
