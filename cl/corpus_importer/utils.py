import itertools
import re
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Iterator, Optional

from django.db.utils import IntegrityError
from django.utils.timezone import now
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from juriscraper.lib.string_utils import harmonize, titlecase

from cl.citations.utils import map_reporter_db_cite_type
from cl.lib.command_utils import logger
from cl.lib.string_diff import get_cosine_similarity
from cl.people_db.lookup_utils import find_all_judges
from cl.search.models import Citation, Docket, OpinionCluster


class OpinionMatchingException(Exception):
    """An exception for wrong matching opinions"""

    def __init__(self, message: str) -> None:
        self.message = message


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


class DocketSourceException(Exception):
    """An exception for wrong docket source"""

    def __init__(self, message: str) -> None:
        self.message = message


class ClusterSourceException(Exception):
    """An exception for wrong cluster source"""

    def __init__(self, message: str) -> None:
        self.message = message


class DateException(Exception):
    """Error found in date merger."""

    def __init__(self, message: str) -> None:
        self.message = message


class EmptyOpinionException(Exception):
    """An exception for opinions that raise a ZeroDivisionError Exception due empty
    opinion tag or empty opinion content in cl"""

    def __init__(self, message: str) -> None:
        self.message = message


async def mark_ia_upload_needed(d: Docket, save_docket: bool) -> None:
    """Mark the docket as needing upload if it's not already marked.

    The point here is that we need to know the first time an item was updated,
    not the *most recent* time it was updated. This way, we know how long it
    has been since it was last uploaded to Internet Archive, and whether it's
    time for us to do so.

    :param d: The docket to mark
    :param save_docket: Whether to save the docket or just modify it in place
    :return: None
    """
    if not d.ia_needs_upload:
        d.ia_needs_upload = True
        d.ia_date_first_change = now()
    if save_docket:
        await d.asave()


def get_start_of_quarter(d: Optional[date] = None) -> date:
    """Get the start date of the  calendar quarter requested

    :param d: The date to get the start date for. If None, then use current
    date/time.
    """
    if d is None:
        d = now().date()

    d_year = d.year
    quarter_dates = [
        date(d_year, 1, 1),
        date(d_year, 4, 1),
        date(d_year, 7, 1),
        date(d_year, 10, 1),
    ]
    return max([q for q in quarter_dates if q <= d])


def make_subset_range(cl_characters: str, max_string: str) -> list[int]:
    """Find indices for matching max_string in CL opinion

    :param cl_characters: The stripped down CL characters
    :param max_string: The current largest identified substring
    :return: Range of indices of match to CL as list
    """
    string_index_start = cl_characters.find(max_string)
    string_index_end = string_index_start + len(max_string)
    return list(range(string_index_start, string_index_end))


def filter_subsets(lists: list[list[int]]) -> Iterator[list[int]]:
    """Filter subsets from matches

    Given list of lists, return new list of lists without subsets

    :param lists: List of matched lists ranges
    :return: Reduced list of matches
    """

    for match in lists:
        if not any(
            is_subset(match, other_matches)
            for other_matches in lists
            if match is not other_matches
        ):
            yield match


def is_subset(match: list[int], other_match: list[int]) -> bool:
    """Check if match is a subset of other matches

    Check if needle is ordered subset of haystack in O(n)

    :param match: Matching range of text as the indices
    :param other_match: Other matching range of text as indices
    :return: Is match a subset of other match
    """

    if len(other_match) < len(match):
        return False
    index = 0
    for element in match:
        try:
            index = other_match.index(element, index) + 1
        except ValueError:
            return False
    else:
        return True


def compare_documents(harvard_characters: str, cl_characters: str) -> int:
    """Compare Harvard text to CL opinion text

    This code iterates over two opinions logging similar stretches and then
    returns a percentage of the total overlapping characters

    :param harvard_characters: The stripped down opinion text from Harvard
    :param cl_characters: The stripped down opinion text on Courtlistener
    :return: Percentage (as integer) overlapping content
    """

    start, stop, count = 0, 0, 0
    matched_substring = ""
    found_overlaps = []
    while stop < len(harvard_characters):
        stop += 1
        harvard_substring = harvard_characters[start:stop]
        if harvard_substring in cl_characters:
            matched_substring = harvard_substring
        else:
            if len(matched_substring) > 5:
                subset = make_subset_range(cl_characters, matched_substring)
                found_overlaps.append(subset)
            matched_substring = ""
            start = stop - 1
    if len(matched_substring) > 5:
        subset = make_subset_range(cl_characters, matched_substring)
        found_overlaps.append(subset)

    # If we checked our subsets as we parsed-we wouldn't need to do this
    # filtering here. This is a good candidate for refactoring.
    filtered_subset = list(filter_subsets(found_overlaps))
    for overlap in filtered_subset:
        count += len(overlap)

    percent_match = int(
        100 * (count / min([len(harvard_characters), len(cl_characters)]))
    )
    return percent_match


def similarity_scores(
    texts_to_compare_1: list[str], texts_to_compare_2: list[str]
) -> list[list[float]]:
    """Get similarity scores between two sets of lists

    Using TF-IDF/Term Frequency-Inverse Document Frequency
    we use word frequency to generate a similarity score between the corpora

    :param texts_to_compare_1: List of text to compare
    :param texts_to_compare_2: List of text to compare
    :return: Return similarity scores
    """

    # We import the library inside the function to avoid loading it if it is
    # not required
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    # Weights the word counts by a measure of how often they appear in the
    # documents, and it returns a sparse matrix
    X = TfidfVectorizer().fit_transform(
        texts_to_compare_1 + texts_to_compare_2
    )

    # Calculate cosine similarity between weight of words for each text in list
    scores = cosine_similarity(
        X[: len(texts_to_compare_1)], X[len(texts_to_compare_1) :]
    )
    return scores


def match_opinion_lists(
    file_opinions_list: list[Any], cl_opinions_list: list[Any]
) -> dict[int, int]:
    """Try to match the opinions on two lists and generate a dict with position of
    matching opinions

    Remove non-alphanumeric and non-whitespace characters from lowercased text,
    this tries to make both texts in equal conditions to prove if both are similar or
    equal

    get_cosine_similarity works great when both texts are almost the same with very
    small variations

    Sometimes cosine similarity fails when there are small variations in text,
    such as parties, attorneys, case name, or court that are included in the content
    of the opinion, compare_documents() checks the percentage of the harvard opinion
    text that it is in courtlistener opinion, having a large percentage means that
    almost all the harvard opinion is in courtlistener opinion, but there is a
    possibility that the courtlistener opinion contains some additional data in que
    opinion content (such as case name, parties, etc.)

    compare_documents works good when the opinion from the file is a subset of the
    opinion in CL, the percentage represents how much of the opinion of the file is
    in the opinion from cl (content in cl opinion can have other data in the body
    like posture, attorneys, etc. e.g. in cluster id: 7643871 we have the posture and
    the opinion text but in the xml file we only have the opinion text, cosine_sim:
    0.1639075094124459 and percent_match: 73)

    Sometimes one algorithm performs better than the other, this is due to some
    additional text, such as editor's notes, or the author, page number or posture
    added to the opinion

    Key is opinion position from file, Value is opinion position from cl opinion e.g.
    matches {0: 1, 1: 2} 0 is file opinion and 1 in cl opinion, 1 is file opinion and
    2 is cl opinion

    :param file_opinions_list: Opinions from file
    :param cl_opinions_list: CL opinions
    :return: Matches if found or empty dict
    """

    scores = similarity_scores(file_opinions_list, cl_opinions_list)

    matches = {}
    for i, row in enumerate(scores):
        j = row.argmax()  # type: ignore
        file_opinion = re.sub(
            r"[^a-zA-Z0-9 ]", "", file_opinions_list[i].lower()
        )
        cl_opinion = re.sub(r"[^a-zA-Z0-9 ]", "", cl_opinions_list[j].lower())

        cosine_sim = get_cosine_similarity(file_opinion, cl_opinion)

        percent_match = compare_documents(file_opinion, cl_opinion)

        if cosine_sim < 0.60 and percent_match < 60:
            continue

        matches[i] = j

    return matches


def clean_docket_number(docket_number: str) -> str:
    """Strip non-numeric content from docket numbers

    :param docket_number: Case docket number
    :return: A stripped down docket number.
    """

    docket_number = re.sub("Department.*", "", docket_number)
    docket_number = re.sub("Nos?. ", "", docket_number)
    return docket_number


def merge_docket_numbers(cluster: OpinionCluster, docket_number: str) -> None:
    """Merge docket number

    :param cluster: The cluster of the merging item
    :param docket_number: The docket number from file
    :return: None
    """
    cl_docket = cluster.docket
    file_cleaned_docket = clean_docket_number(docket_number)

    if cl_docket.docket_number:
        # Check if docket number exists
        # e.g. CL docket id #3952066 doesn't have
        cl_clean_docket = clean_docket_number(cl_docket.docket_number)
        if (
            cl_clean_docket in file_cleaned_docket
            and cl_docket.docket_number != file_cleaned_docket
        ):
            cl_docket.docket_number = file_cleaned_docket
            cl_docket.save()
        else:
            # Check if their relatively similar and if so save the columbia one
            # if its longer
            similarity = get_cosine_similarity(
                cl_clean_docket, file_cleaned_docket
            )
            if similarity > 0.8:
                if len(file_cleaned_docket) > len(cl_clean_docket):
                    cl_docket.docket_number = file_cleaned_docket
                    cl_docket.save()
    else:
        # CL docket doesn't have a docket number, add the one from json file
        cl_docket.docket_number = file_cleaned_docket
        cl_docket.save()


def merge_case_names(
    cluster: OpinionCluster,
    file_data: dict[str, Any],
    case_name_key: str,
    case_name_full_key: str,
) -> dict[str, Any]:
    """Merge case names

    :param cluster: The cluster of the merging item
    :param file_data: json data from file(columbia, harvard, etc.)
    :param case_name_key: dict key that contains case_name value from file
    :param case_name_full_key: dict key that contains case_name_key value from file
    :return: empty dict or dict with new value for field
    """
    columbia_case_name = titlecase(harmonize(file_data[case_name_key]))
    columbia_case_name_full = titlecase(file_data[case_name_full_key])
    cluster_case_name = titlecase(harmonize(cluster.case_name))
    cluster_case_name_full = titlecase(cluster.case_name_full)

    update_dict = {}
    # Case with full case names
    if not cluster_case_name_full and columbia_case_name_full:
        update_dict["case_name_full"] = columbia_case_name_full
        # Change stored value to new
        cluster_case_name_full = columbia_case_name_full
    elif cluster_case_name_full and columbia_case_name_full:
        if len(columbia_case_name_full) > len(cluster_case_name_full):
            # Select best case name based on string length
            update_dict["case_name_full"] = columbia_case_name_full
            # Change stored value to new
            cluster_case_name_full = columbia_case_name_full
    else:
        # We don't care if data is empty or both are empty
        pass

    # Case with abbreviated case names
    if not cluster_case_name and columbia_case_name:
        update_dict["case_name"] = columbia_case_name
        # Change stored value to new
        cluster_case_name = columbia_case_name
    elif cluster_case_name and columbia_case_name:
        if len(columbia_case_name) > len(cluster_case_name):
            # Select best case name based on string length
            update_dict["case_name"] = columbia_case_name
            # Change stored value to new
            cluster_case_name = columbia_case_name
    else:
        # We don't care if data is empty or both are empty
        pass

    if cluster_case_name_full and cluster_case_name:
        if len(cluster_case_name) > len(cluster_case_name_full):
            # Swap field values
            update_dict["case_name"] = cluster_case_name_full
            update_dict["case_name_full"] = cluster_case_name

    return update_dict


def merge_strings(
    field_name: str, overlapping_data: tuple[str, str]
) -> dict[str, Any]:
    """Compare two strings and choose the largest

    :param field_name: field name to update in opinion cluster
    :param overlapping_data: data to compare from file and courtlistener
    :return: empty dict or dict with new value for field
    """
    if not overlapping_data:
        return {}

    file_data, cl_data = overlapping_data
    if len(file_data) > len(cl_data):
        return {field_name: file_data}

    return {}


def merge_long_fields(
    field_name: str,
    overlapping_data: Optional[tuple[str, str]],
    cluster_id: int,
) -> dict[str, Any]:
    """Merge two long text fields

    :param field_name: Field name to update in opinion cluster
    :param overlapping_data: data to compare from columbia and courtlistener
    :param cluster_id: cluster id
    :return: empty dict or dict with new value for field
    """
    if not overlapping_data:
        return {}

    file_data, cl_data = overlapping_data
    # Do some text comparison
    similarity = get_cosine_similarity(file_data, cl_data)
    if similarity < 0.9:
        # they are not too similar, choose the larger one
        if len(file_data) > len(cl_data):
            return {field_name: file_data}

    else:
        if similarity <= 0.5:
            logger.info(
                f"The content compared is very different. Cluster id: {cluster_id}"
            )
    return {}


def merge_judges(
    overlapping_data: Optional[tuple[str, str]],
    cluster_id: int,
    is_columbia: bool = False,
    skip_judge_merger: bool = False,
) -> dict[str, Any]:
    """Merge overlapping judge values

    :param overlapping_data: data to compare from file and courtlistener
    :param cluster_id: opinion cluster id
    :param is_columbia: True if merging judges from columbia
    :param skip_judge_merger: skip judge merger instead of raise exception
    :return: empty dict or dict with new value for field
    """

    if not overlapping_data:
        return {}

    file_data, cl_data = overlapping_data
    # We check if any word in the string is uppercase
    cl_data_upper = (
        True if [s for s in cl_data.split(",") if s.isupper()] else False
    )

    # Get last names keeping case and cleaning the string (We could have
    # the judge names in capital letters)
    cl_clean = set(find_all_judges(cl_data))
    # Lowercase courtlistener judge names for set operations
    temp_cl_clean = set([c.lower() for c in cl_clean])
    # Get last names in lowercase and cleaned
    file_data_cleaned = set(find_all_judges(file_data))
    # Lowercase file judge names for set operations
    temp_file_data_clean = set([h.lower() for h in file_data_cleaned])
    # Prepare judges string
    judges = titlecase(", ".join(find_all_judges(file_data)))
    if (
        temp_file_data_clean.issuperset(temp_cl_clean) or cl_data_upper
    ) and file_data_cleaned != cl_clean:
        return {"judges": judges}
    elif not temp_file_data_clean.intersection(temp_cl_clean):
        # Last resort, use distance between words to solve typos
        cl_data_clean_list = list(cl_clean)
        file_data_clean_list = list(file_data_cleaned)
        judge_pairs = list(
            itertools.product(cl_data_clean_list, file_data_clean_list)
        )
        success = False
        for pair in judge_pairs:
            s = SequenceMatcher(None, pair[0].lower(), pair[1].lower())
            if s.ratio() >= 0.7:
                # We found a match
                try:
                    if is_columbia:
                        # we assume that the data in columbia is better, we keep the
                        # one from columbia and remove the one from cl
                        cl_data_clean_list.remove(pair[0])
                    else:
                        # we assume that the data in CL is better, we keep the one from
                        # CL and remove the one from harvard
                        file_data_clean_list.remove(pair[1])
                except ValueError:
                    # The value was removed in an earlier iteration, but we still
                    # have the value in the remaining pairs to match, we simply
                    # ignore it
                    pass
                success = True

        if success:
            # At least one success that matches the names, we can create a new judges
            # list
            new_judges_list = sorted(
                list(set(cl_data_clean_list + file_data_clean_list))
            )
            return {"judges": titlecase(", ".join(new_judges_list))}
        else:
            if skip_judge_merger:
                # Fail silently but continue to merge
                logger.info(
                    f"Can't merge judges, something failed, cluster id: {cluster_id}"
                )
                return {}
            else:
                # Stop merge raising an exception
                raise JudgeException("Judges are completely different.")

    return {}


def merge_overlapping_data(
    cluster: OpinionCluster,
    long_fields,
    changed_values_dictionary: dict,
    skip_judge_merger: bool = False,
    is_columbia: bool = False,
) -> dict[str, Any]:
    """Merge overlapping data

    :param cluster: the cluster object
    :param long_fields: skip judge merger
    :param changed_values_dictionary: the dictionary of data to merge
    :param skip_judge_merger: skip judge merger

    :param is_columbia: skip judge merger
    :return: empty dict or dict with new values for fields
    """

    if not changed_values_dictionary:
        # Empty dictionary means that we don't have overlapping data
        return {}

    data_to_update = {}

    for field_name in changed_values_dictionary.keys():
        if field_name in long_fields:
            data_to_update.update(
                merge_long_fields(
                    field_name,
                    changed_values_dictionary.get(field_name),
                    cluster.id,
                )
            )
        elif field_name == "attorneys":
            data_to_update.update(
                merge_strings(
                    field_name,
                    changed_values_dictionary.get(field_name, ""),
                )
            )
        elif field_name == "judges":
            data_to_update.update(
                merge_judges(
                    changed_values_dictionary.get(field_name, ""),
                    cluster.id,
                    is_columbia=is_columbia,
                    skip_judge_merger=skip_judge_merger,
                )
            )
        else:
            logger.info(f"Field not considered in the process: {field_name}")

    return data_to_update


def add_citations_to_cluster(cites: list[str], cluster_id: int) -> None:
    """Add string citations to OpinionCluster if it has not yet been added

    :param cites: citation list
    :param cluster_id: cluster id related to citations
    :return: None
    """
    for cite in cites:
        clean_cite = re.sub(r"\s+", " ", cite)
        citation = get_citations(clean_cite)
        if (
            not citation
            or not isinstance(citation[0], FullCaseCitation)
            or not citation[0].groups.get("volume", False)
        ):
            logger.warning(f"Citation parsing failed for {clean_cite}")
            continue

        if not citation[0].corrected_reporter():
            reporter_type = Citation.STATE
        else:
            cite_type_str = citation[0].all_editions[0].reporter.cite_type
            reporter_type = map_reporter_db_cite_type(cite_type_str)

        try:
            o, created = Citation.objects.get_or_create(
                volume=citation[0].groups["volume"],
                reporter=citation[0].corrected_reporter(),
                page=citation[0].groups["page"],
                type=reporter_type,
                cluster_id=cluster_id,
            )
            if created:
                logger.info(
                    f"New citation: {cite} added to cluster id: {cluster_id}"
                )
        except IntegrityError:
            logger.warning(
                f"Reporter mismatch for cluster: {cluster_id} on cite: {cite}"
            )

    pass
