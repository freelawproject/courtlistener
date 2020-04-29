
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from cl.api.utils import HyperlinkedModelSerializerWithId
from cl.visualizations.models import SCOTUSMap
from cl.search.models import (
  OpinionCluster
)
from cl.recap.models import (
  ProcessingQueue
)

class VisualizationSerializer(serializers.ModelSerializer):
  class Meta:
    model = SCOTUSMap
    fields = ['id', 'title', 'cluster_start', 'cluster_end']

class CreateVisualizationSerializer(serializers.ModelSerializer):
  uploader = serializers.HiddenField(
    default=serializers.CurrentUserDefault(),
  )
  title = serializers.CharField(max_length=200)
  cluster_start = serializers.PrimaryKeyRelatedField(
    queryset=OpinionCluster.objects.all(),
    style={'base_template': 'select.html'}
  )
  cluster_end = serializers.PrimaryKeyRelatedField(
    queryset=OpinionCluster.objects.all(),
    style={'base_template': 'select.html'}
  )

  class Meta:
    model = SCOTUSMap
    exclude = ("uploader") # Private

  def validate(self, attrs):
    for attr_name in [
      "cluster_start",
      "cluster_end"
    ]:
      if not attrs.get(attr_name):
        raise ValidationError("%s is required!" % attr_name)
      if attrs.get(attr_name) == "undefined":
        raise ValidationError(
          "%s field cannot have the literal value 'undefined'" % attr_name
        )

    return attrs