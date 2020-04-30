from rest_framework import viewsets

from cl.api.utils import LoggingMixin

from cl.visualizations.api_serializers import CreateVisualizationSerializer

from cl.visualizations.models import SCOTUSMap


class VisualizationViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = SCOTUSMap.objects.all()
    serializer_class = CreateVisualizationSerializer
    ordering_fields = ("id", "date_created", "date_modified", "user")
