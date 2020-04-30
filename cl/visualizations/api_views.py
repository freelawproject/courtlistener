from rest_framework import viewsets

from cl.api.utils import LoggingMixin

from cl.visualizations.api_serializers import VisualizationSerializer

from cl.visualizations.models import SCOTUSMap

class VisualizationViewSet(LoggingMixin, viewsets.ModelViewSet):
    queryset = SCOTUSMap.objects.all()
    serializer_class = VisualizationSerializer
    ordering_fields = ("id", "date_created", "date_modified", "user")
