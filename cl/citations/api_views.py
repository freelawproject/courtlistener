from http import HTTPStatus

import eyecite
from asgiref.sync import async_to_sync
from django.db.models import QuerySet
from django.http import HttpResponse
from django.template.defaultfilters import slugify
from reporters_db import EDITIONS
from rest_framework.exceptions import NotFound
from rest_framework.mixins import ListModelMixin
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from cl.api.pagination import MediumAdjustablePagination
from cl.citations.api_serializers import CitationRequestSerializer
from cl.citations.exceptions import MultipleChoices
from cl.citations.utils import get_canonicals_from_reporter
from cl.search.api_serializers import OpinionClusterSerializer
from cl.search.models import OpinionCluster
from cl.search.selectors import get_clusters_from_citation_str

SLUGIFIED_EDITIONS: dict[str, str] = {
    str(slugify(item)): item for item in EDITIONS.keys()
}


class CitationLookupViewSet(ListModelMixin, GenericViewSet):
    queryset = OpinionCluster.objects.all()
    pagination_class = MediumAdjustablePagination
    serializer = OpinionClusterSerializer

    def list(self, request: Request, *args, **kwargs):
        query = request.query_params

        # Uses the serializer to perform object level validations
        citation_serializer = CitationRequestSerializer(data=query)
        citation_serializer.is_valid(raise_exception=True)

        # Get query parameters from the validated data
        data = citation_serializer.validated_data
        self.full_text_citation = data.get("text_citation", None)
        self.reporter = data.get("reporter", None)
        self.volume = data.get("volume", None)
        self.page = data.get("citation_page", None)

        if self.full_text_citation:
            citations = eyecite.get_citations(self.full_text_citation)
            if not citations:
                raise NotFound(
                    f"Unable to find a citation withing the provided text"
                )

            if citations[0].groups:
                c = citations[0]
                self.reporter = slugify(c.groups["reporter"])
                self.volume = c.groups["volume"]
                self.page = c.groups["page"]
            else:
                raise NotFound(
                    f"The provided text is not a valid citation. Please review it and try again"
                )

        self.reporter_slug = slugify(self.reporter)

        # Look up the reporter to get its proper version (so-2d -> So. 2d)
        proper_reporter = SLUGIFIED_EDITIONS.get(self.reporter_slug, None)
        if not proper_reporter:
            proper_reporter = self._attempt_reporter_variation()

        if proper_reporter and self.volume and self.page:
            return self._citation_handler(request, proper_reporter)
        else:
            return self._reporter_volume_handler(request, proper_reporter)

    def _attempt_reporter_variation(self) -> str:
        """Try to disambiguate an unknown reporter using the variations dict.

        Raises:
            NotFound: If the unknown reporter string doesn't match a canonical.
            MultipleChoices: If the reporter variation maps to more than one
                            canonical reporter.

        Returns:
            str: canonical name for the reporter.
        """
        potential_canonicals = get_canonicals_from_reporter(self.reporter_slug)

        if len(potential_canonicals) == 0:
            # Couldn't find it as a variation. Give up.
            raise NotFound(
                f"Unable to find Reporter with abbreviation of '{self.reporter}'"
            )

        elif len(potential_canonicals) > 1:
            # The reporter variation is ambiguous b/c it can refer to more than
            # one reporter. Abort with a 300 status.
            raise MultipleChoices(
                f"Found more than one possible reporter for '{self.reporter}'"
            )

        else:
            # Unambiguous reporter variation. Use the canonical reporter
            return SLUGIFIED_EDITIONS.get(potential_canonicals[0], "")

    def _citation_handler(
        self, request: Request, reporter: str
    ) -> HttpResponse:
        """
        This method retrieves opinion clusters that match a citation string.

        Args:
            request (Request): The HTTP object containing information
                about the request.
            reporter (str): The name of the reporter.

        Raises:
            NotFound: If the citation string doesn't match any opinion clusters

        Returns:
            HttpResponse: An HTTP response object containing a list of matching
                opinion clusters.
        """
        citation_str = " ".join([str(self.volume), reporter, self.page])
        clusters, cluster_count = async_to_sync(
            get_clusters_from_citation_str
        )(reporter, str(self.volume), self.page)

        if cluster_count == 0:
            raise NotFound(f"Unable to Find Citation '{ citation_str }'")

        return self._show_paginated_response(request, clusters)

    def _reporter_volume_handler(
        self, request: Request, reporter: str
    ) -> HttpResponse:
        """
        Handles requests to retrieve opinions based on a reporter-volume
        combination.

        Args:
            request (Request): The HTTP object containing information
                about the request.
            reporter (str): The name of the reporter.

        Returns:
            A response object containing the list of opinions for the
            reporter-volume dyad.

        Raises:
            NotFound: If the reporter name is invalid or the reporter-volume
                combination doesn't match any opinion clusters.
        """
        root_reporter = EDITIONS.get(reporter)
        if not root_reporter:
            raise NotFound(
                f"Unable to find Reporter with abbreviation of '{reporter}'"
            )

        cases_in_volume = OpinionCluster.objects.filter(
            citations__reporter=reporter, citations__volume=self.volume
        ).order_by("date_filed")

        if not cases_in_volume.exists():
            raise NotFound(
                f"Unable to Find any Citations for { self.volume } ( {reporter} )"
            )

        return self._show_paginated_response(request, cases_in_volume)

    def _show_paginated_response(
        self, request: Request, clusters: QuerySet[OpinionCluster]
    ) -> HttpResponse:
        """
        Generates a paginated HTTP response containing opinion clusters.

        This method takes a queryset of opinion clusters and an HTTP request
        object.It then paginates the queryset based on the request parameters
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
        paginator = self.pagination_class()
        result_page = paginator.paginate_queryset(clusters, request)
        serializer = self.serializer(
            result_page, many=True, context={"request": request}
        )
        return Response(
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "results": serializer.data,
            },
            status=(
                HTTPStatus.MULTIPLE_CHOICES
                if clusters.count() > 1
                else HTTPStatus.OK
            ),
        )
