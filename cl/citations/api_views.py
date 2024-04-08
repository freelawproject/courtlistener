from http import HTTPStatus

import eyecite
from asgiref.sync import async_to_sync
from django.conf import settings
from django.db.models import QuerySet
from django.template.defaultfilters import slugify
from django.utils.safestring import SafeString
from rest_framework.exceptions import NotFound
from rest_framework.mixins import CreateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from cl.citations.api_serializers import (
    CitationAPIRequestSerializer,
    CitationAPIResponseSerializer,
)
from cl.citations.types import CitationAPIResponse
from cl.citations.utils import (
    SLUGIFIED_EDITIONS,
    filter_out_non_case_law_and_non_valid_citations,
    get_canonicals_from_reporter,
)
from cl.search.models import OpinionCluster
from cl.search.selectors import get_clusters_from_citation_str


class CitationLookupViewSet(CreateModelMixin, GenericViewSet):
    queryset = OpinionCluster.objects.all()
    serializer_class = CitationAPIRequestSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request: Request, *args, **kwargs):
        # Uses the serializer to perform object level validations
        citation_serializer = CitationAPIRequestSerializer(data=request.data)
        citation_serializer.is_valid(raise_exception=True)

        # Get query parameters from the validated data
        citations = []
        data = citation_serializer.validated_data
        text = data.get("text", None)
        if text:
            citation_objs = eyecite.get_citations(text)
            citation_objs = filter_out_non_case_law_and_non_valid_citations(
                citation_objs
            )
            if not citation_objs:
                return Response([])

            for idx, citation in enumerate(citation_objs):

                start_index, end_index = citation.span()
                citation_data = {
                    "citation": citation.matched_text(),
                    "normalized_citations": [citation.corrected_citation()],
                    "start_index": start_index,
                    "end_index": end_index,
                }

                if idx == settings.MAX_CITATIONS_PER_REQUEST:
                    citations.append(
                        {
                            **citation_data,
                            "status": HTTPStatus.TOO_MANY_REQUESTS,
                            "error_message": "Too many requests.",
                        }
                    )
                    break

                reporter = citation.groups["reporter"]
                volume = citation.groups["volume"]
                page = citation.groups["page"]
                citations.append(
                    {
                        **citation_data,
                        **self._citation_handler(
                            request, reporter, volume, page
                        ),
                    }
                )
        else:
            reporter = data.get("reporter")
            volume = data.get("volume")
            page = data.get("page")

            citation_str = " ".join([str(volume), reporter, page])
            citation_data = {
                "citation": citation_str,
                "start_index": 0,
                "end_index": len(citation_str),
            }
            citations.append(
                {
                    **citation_data,
                    **self._citation_handler(request, reporter, volume, page),
                }
            )

        return Response(
            CitationAPIResponseSerializer(
                citations, many=True, context={"request": request}
            ).data
        )

    def _attempt_reporter_variation(self, reporter) -> list[SafeString]:
        """Try to disambiguate an unknown reporter using the variations dict.

        Args:
            reporter (str): The name of the reporter.

        Raises:
            NotFound: If the unknown reporter string doesn't match a canonical.

        Returns:
            str: canonical name for the reporter.
        """
        potential_canonicals = get_canonicals_from_reporter(slugify(reporter))

        if len(potential_canonicals) == 0:
            # Couldn't find it as a variation. Give up.
            raise NotFound(
                f"Unable to find reporter with abbreviation of '{reporter}'"
            )

        return potential_canonicals

    def _citation_handler(
        self, request: Request, reporter: str, volume: int, page: str
    ) -> CitationAPIResponse:
        """
        This method retrieves opinion clusters that match a citation string.

        Args:
            request (Request): The HTTP object containing information
                about the request.
            reporter (str): The name of the reporter.
            volume (int): The volume number of citation.
            page (str): The page number where the citation is located.

        Raises:
            NotFound: If the citation string doesn't match any opinion clusters

        """
        # Look up the reporter to get its proper version (so-2d -> So. 2d)
        proper_reporter: None | str | list[SafeString]
        proper_reporter = SLUGIFIED_EDITIONS.get(slugify(reporter), None)
        if not proper_reporter:
            try:
                proper_reporter = self._attempt_reporter_variation(reporter)
            except NotFound as e:
                return {
                    "normalized_citations": [],
                    "status": HTTPStatus.BAD_REQUEST,
                    "error_message": str(e.detail),
                }

        normalized_citations = []
        if isinstance(proper_reporter, str):
            # We retrieved the proper_reporter directly from the
            # SLUGIFIED_EDITIONS dictionary.
            normalized_citations.append(
                " ".join([str(volume), proper_reporter, page])
            )
            clusters, cluster_count = async_to_sync(
                get_clusters_from_citation_str
            )(proper_reporter, str(volume), page)
        else:
            clusters, cluster_count, normalized_citations = (
                self._get_clusters_for_canonical_list(
                    proper_reporter, volume, page
                )
            )

        if not cluster_count:
            citation_str = " ".join([str(volume), reporter, page])
            return {
                "normalized_citations": normalized_citations,
                "status": HTTPStatus.NOT_FOUND,
                "error_message": f"Citation not found: '{ citation_str }'",
            }

        return {
            "normalized_citations": normalized_citations,
            **self._format_cluster_response(clusters, cluster_count),
        }

    def _get_clusters_for_canonical_list(
        self, reporters: list[SafeString], volume: int, page: str
    ) -> tuple[QuerySet[OpinionCluster] | None, int, list[str]]:
        """
        Retrieves opinion clusters associated with a list of reporter slugs.

        This method takes a list of reporter variations (as slugs) and attempts
        to find all associated opinion clusters.

        Args:
            reporters (list[SafeString]): A list of strings representing the reporter
                                  slugs.
            volume (int): The volume number of citation.
            page (str): The page number where the citation is located.

        Returns:
            A tuple containing three elements:
                - A list of the matching opinion clusters.
                - An integer representing the total number of matching opinion
                clusters found for the given reporters.
                - A list with the normalized citations.
        """
        clusters, cluster_count, citations = None, 0, []
        for canonical in reporters:
            reporter = SLUGIFIED_EDITIONS.get(canonical, None)
            if not reporter:
                continue
            citations.append(" ".join([str(volume), reporter, page]))
            opinions, _count = async_to_sync(get_clusters_from_citation_str)(
                reporter, str(volume), page
            )

            if not _count:
                continue

            clusters = clusters | opinions if clusters else opinions
            cluster_count += _count
        return clusters, cluster_count, citations

    def _format_cluster_response(
        self,
        clusters: QuerySet[OpinionCluster],
        cluster_count: int,
    ) -> CitationAPIResponse:
        """
        Enhances the provided cluster queryset and formats the data
        for the response.

        Args:
            request (Request): The HTTP request object.
            clusters (QuerySet[OpinionCluster]): The queryset containing
            opinion clusters.
            cluster_count (int): The expected number of clusters.

        Returns:
            A dictionary containing the following keys:
                - status (int): An integer indicating the status of the operation.
                - clusters (Queryset): queryset of cluster that contains relevant
                    data from the cluster model and its associated models.
        """
        clusters = clusters.prefetch_related(
            "sub_opinions", "panel", "non_participating_judges", "citations"
        ).order_by("-id")
        return {
            "status": (
                HTTPStatus.MULTIPLE_CHOICES
                if cluster_count > 1
                else HTTPStatus.OK
            ),
            "clusters": clusters,
        }
