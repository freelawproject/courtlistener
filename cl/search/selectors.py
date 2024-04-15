import natsort
from django.db.models import F, Prefetch, QuerySet

from cl.search.models import OpinionCluster


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
        clusters = (
            OpinionCluster.objects.filter(citation=citation_str)
            .select_related("docket")
            .prefetch_related(Prefetch("docket__court", to_attr="court_data"))
        )
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
            opinion
            async for opinion in OpinionCluster.objects.filter(
                citations__reporter=reporter, citations__volume=volume
            )
            .annotate(cite_page=(F("citations__page")))
            .values_list("id", "cite_page")
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
            clusters = (
                OpinionCluster.objects.filter(
                    id=possible_match.id,
                    sub_opinions__html_with_citations__contains=f"*{page}",
                )
                .select_related("docket")
                .prefetch_related(
                    Prefetch("docket__court", to_attr="court_data")
                )
            )
            cluster_count = 1 if await clusters.aexists() else 0

    return clusters, cluster_count
