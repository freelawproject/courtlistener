import natsort
from django.db import connection
from django.db.models import Q, QuerySet

from cl.search.models import Citation, OpinionCluster


def get_available_documents_estimate_count() -> int:
    with connection.cursor() as cursor:
        cursor.execute("""
            WITH stats AS (
              SELECT
                most_common_vals,
                most_common_freqs,
                array_position(most_common_vals::text::text[], 't') AS index
              FROM pg_stats
              WHERE tablename = 'search_recapdocument' AND attname = 'is_available'
            ),
            doc_estimate AS (
              SELECT reltuples::bigint AS estimate
              FROM pg_class
              WHERE oid = 'public.search_recapdocument'::regclass
            )
            SELECT
              (most_common_freqs[index] * estimate)::bigint AS estimated_true_count
            FROM stats, doc_estimate
            WHERE index IS NOT NULL;
        """)
        result = cursor.fetchone()
        return result[0] if result else None


async def get_clusters_from_citation_str(
    reporter: str, volume: str, page: str
) -> tuple[QuerySet[OpinionCluster] | None, int]:
    """
    This function attempts to retrieve opinion clusters related to a citation
    string.

    This helper first tries to find an exact match of the citation string within
    our OpinionCluster records. If no exact match is found, the helper searches
    citation strings immediately preceding the requested one in the same book.

    Args:
        reporter (str): The reporter of the citation.
        volume (str): The volume number of citation.
        page (str): The page number where the citation is located.

    Returns:
        A tuple containing two elements:
            - A list of the matching opinion clusters.
            - An integer representing the number of matching opinion clusters
            found.
    """
    citation_str = " ".join([volume, reporter, page])
    clusters = None
    try:
        clusters = OpinionCluster.objects.filter(
            citation=citation_str
        ).select_related("docket__court")
    except ValueError:
        # Unable to parse the citation.
        cluster_count = 0
    else:
        cluster_count = await clusters.acount()

    if cluster_count == 0:
        # We didn't get an exact match on the volume/reporter/page. Perhaps
        # it's a pincite. Try to find the citation immediately *before* this
        # one in the same book. To do so, get all the opinions from the book,
        # sort them by page number (in Python, b/c pages can have letters),
        # then find the citation just before the requested one.

        possible_match = None

        # Create a list of the closest opinion clusters id and page to the
        # input citation
        closest_opinion_clusters = [
            c
            async for c in Citation.objects.filter(
                reporter=reporter, volume=volume
            ).values_list("cluster_id", "page")
        ]

        # Create a temporal item and add it to the values list
        citation_item = (0, page)
        closest_opinion_clusters.append((0, page))

        # Natural sort page numbers ascending order
        sort_possible_matches = natsort.natsorted(
            closest_opinion_clusters, key=lambda item: item[1]
        )

        # Find the position of the item that we added
        citation_item_position = sort_possible_matches.index(citation_item)

        if citation_item_position > 0:
            # if the position is greater than 0, then the previous item in
            # the list is the closest citation, we get the id of the
            # previous item, and we get the object
            possible_match = await OpinionCluster.objects.aget(
                id=sort_possible_matches[citation_item_position - 1][0]
            )

        if possible_match:
            # There may be different page cite formats that aren't yet
            # accounted for by this code.
            clusters = OpinionCluster.objects.filter(
                Q(id=possible_match.id),
                Q(sub_opinions__html_with_citations__contains=f"*{page}")
                | Q(sub_opinions__xml_harvard__contains=f"*{page}"),
            ).select_related("docket__court")
            cluster_count = 1 if await clusters.aexists() else 0

    return clusters, cluster_count
