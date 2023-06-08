from datetime import date
from typing import Any, Optional

from django.utils.timezone import now

from cl.lib.string_diff import get_cosine_similarity
from cl.search.models import Docket


def mark_ia_upload_needed(d: Docket, save_docket: bool) -> None:
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
        d.save()


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


def match_lists(
    harvard_opinions_list: list[str], cl_opinions_list: list[str]
) -> dict[int, Any]:
    """Generate matching lists above threshold

    :param harvard_opinions_list: Harvard Opinions
    :param cl_opinions_list: CL opinions
    :return: Matches if found or False
    """
    # We import this here to avoid a circular import
    from cl.corpus_importer.management.commands.harvard_opinions import (
        compare_documents,
    )

    # Convert harvard HTML to Text to compare
    harvard_opinions_list = [h.getText() for h in harvard_opinions_list]
    scores = similarity_scores(harvard_opinions_list, cl_opinions_list)

    matches = {}
    for i, row in enumerate(scores):
        j = row.argmax()  # type: ignore
        # Lower threshold for small opinions.
        if (
            get_cosine_similarity(
                harvard_opinions_list[i], cl_opinions_list[j]
            )
            < 0.60
        ):
            continue
        percent_match = compare_documents(
            harvard_opinions_list[i], cl_opinions_list[j]
        )
        if percent_match < 60:
            continue
        matches[i] = j

    return matches
