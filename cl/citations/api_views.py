from http import HTTPStatus

import eyecite
from asgiref.sync import async_to_sync
from django.db.models import QuerySet
from django.http import HttpResponse
from django.template.defaultfilters import slugify
from django.utils.safestring import SafeString
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.mixins import CreateModelMixin
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from cl.citations.api_serializers import CitationRequestSerializer
from cl.citations.utils import SLUGIFIED_EDITIONS, get_canonicals_from_reporter
from cl.search.api_serializers import OpinionClusterSerializer
from cl.search.models import OpinionCluster
from cl.search.selectors import get_clusters_from_citation_str


class CitationLookupViewSet(CreateModelMixin, GenericViewSet):
    queryset = OpinionCluster.objects.all()
    serializer = OpinionClusterSerializer

    def create(self, request: Request, *args, **kwargs):
        # Uses the serializer to perform object level validations
        citation_serializer = CitationRequestSerializer(data=request.data)
        citation_serializer.is_valid(raise_exception=True)

        # Get query parameters from the validated data
        citations = []
        data = citation_serializer.validated_data
        full_text_citation = data.get("text_citation", None)
        if full_text_citation:
            citation_objs = eyecite.get_citations(full_text_citation)
            if not citation_objs:
                raise NotFound(f"No citations found in 'text_citation'.")

            for citation in citation_objs:
                start_index, end_index = citation.span()
                citation_data = {
                    "citation": citation.matched_text(),
                    "start_index": start_index,
                    "end_index": end_index,
                }
                if not citation.groups:
                    error_data = {
                        "status": HTTPStatus.BAD_REQUEST,
                        "error_message": "Invalid citation.",
                    }
                    citations.append({**citation_data, **error_data})
                    continue

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

            citations.append(
                {
                    "citation": " ".join([str(volume), reporter, page]),
                    **self._citation_handler(request, reporter, volume, page),
                }
            )

        return Response(citations)

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
    ) -> HttpResponse:
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

        Returns:
            HttpResponse: An HTTP response object containing a list of matching
                opinion clusters.
        """
        citation_str = " ".join([str(volume), reporter, page])

        # Look up the reporter to get its proper version (so-2d -> So. 2d)
        proper_reporter: None | str | list[SafeString]
        proper_reporter = SLUGIFIED_EDITIONS.get(slugify(reporter), None)
        if not proper_reporter:
            proper_reporter = self._attempt_reporter_variation()

        if isinstance(proper_reporter, str):
            # We retrieved the proper_reporter directly from the
            # SLUGIFIED_EDITIONS dictionary.
            clusters, cluster_count = async_to_sync(
                get_clusters_from_citation_str
            )(proper_reporter, str(volume), page)
        else:
            clusters, cluster_count = self._get_clusters_for_canonical_list(
                proper_reporter, volume, page
            )

        if cluster_count == 0:
            raise NotFound(f"Citation not found: '{ citation_str }'")

        return self._show_response(request, clusters)

    def _get_clusters_for_canonical_list(
        self, reporters: list[SafeString], volume: int, page: str
    ) -> tuple[QuerySet[OpinionCluster] | None, int]:
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
            A tuple containing two elements:
                - A list of the matching opinion clusters.
                - An integer representing the total number of matching opinion
                clusters found for the given reporters.
        """
        clusters, cluster_count = None, 0
        for canonical in reporters:
            reporter = SLUGIFIED_EDITIONS.get(canonical, None)
            if not reporter:
                continue

            opinions, _count = async_to_sync(get_clusters_from_citation_str)(
                reporter, str(volume), page
            )

            if not _count:
                continue

            clusters = clusters | opinions if clusters else opinions
            cluster_count += _count
        return clusters, cluster_count

    def _show_response(
        self, request: Request, clusters: QuerySet[OpinionCluster]
    ) -> HttpResponse:
        """
        Generates a paginated HTTP response containing opinion clusters.

        This method takes a queryset of opinion clusters and an HTTP request
        object. It then paginates the queryset based on the request parameters
        and returns an appropriate HTTP response containing the paginated data.

        Args:
            request (Request): The HTTP request object.
            clusters (QuerySet[OpinionCluster]): The queryset containing opinion
            clusters.

        Returns:
            HttpResponse: An HTTP response containing the paginated opinion
                        clusters and pagination information.
        """
        clusters = clusters.prefetch_related(
            "sub_opinions", "panel", "non_participating_judges", "citations"
        ).order_by("-id")
        serializer = self.serializer(
            clusters, many=True, context={"request": request}
        )
        return Response(
            serializer.data,
            status=(
                HTTPStatus.MULTIPLE_CHOICES
                if clusters.count() > 1
                else HTTPStatus.OK
            ),
        )
