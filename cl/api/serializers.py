from collections import OrderedDict

from cl.audio import models as audio_models
from cl.lib.sunburnt import schema
from cl.lib.sunburnt.schema import SolrSchema
from cl.search import models as search_models

from rest_framework import serializers


class DocketSerializer(serializers.HyperlinkedModelSerializer):
    court = serializers.HyperlinkedRelatedField(
        many=False,
        view_name='court-detail',
        read_only=True,
    )
    clusters = serializers.HyperlinkedRelatedField(
        many=True,
        view_name='opinioncluster-detail',
        read_only=True,
    )
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)

    class Meta:
        model = search_models.Docket


class CourtSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = search_models.Court
        exclude = ('notes',)


class AudioSerializer(serializers.HyperlinkedModelSerializer):
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)

    class Meta:
        model = audio_models.Audio


class OpinionClusterSerializer(serializers.HyperlinkedModelSerializer):
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)

    class Meta:
        model = search_models.OpinionCluster


class OpinionSerializer(serializers.HyperlinkedModelSerializer):
    absolute_url = serializers.CharField(source='get_absolute_url',
                                         read_only=True)

    class Meta:
        model = search_models.Opinion


class OpinionsCitedSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = search_models.OpinionsCited


class SearchResultSerializer(serializers.Serializer):
    """The serializer for search results.
    """
    solr_field_mappings = {
        schema.SolrBooleanField: serializers.BooleanField,
        schema.SolrUnicodeField: serializers.CharField,
        schema.SolrUUIDField: serializers.CharField,
        schema.SolrDateField: serializers.DateTimeField,

        # Numbers
        schema.SolrNumericalField: serializers.IntegerField,
        schema.SolrShortField: serializers.IntegerField,
        schema.SolrIntField: serializers.IntegerField,
        schema.SolrLongField: serializers.IntegerField,
        schema.SolrFloatField: serializers.FloatField,
        schema.SolrDoubleField: serializers.IntegerField,
    }
    solr_data_types = SolrSchema.solr_data_types
    solr_data_types.update({
        'solr.ExternalFileField': schema.SolrUnicodeField
    })
    skipped_fields = ['_version_', 'django_ct', 'django_id', 'text']

    def get_fields(self):
        """Return a list of fields so that they don't have to be declared one
        by one and updated whenever there's a new field.
        """
        fields = {
            'snippet': serializers.CharField(read_only=True),
        }
        # Map each field in the Solr schema to a DRF field
        for field_name, field_obj in self._context['schema'].fields.items():
            drf_field = self._get_drf_field(field_obj)
            fields[field_name] = drf_field(read_only=True)

        for field in self.skipped_fields:
            fields.pop(field)
        fields = OrderedDict(sorted(fields.items()))  # Sort by key
        return fields

    def _get_drf_field(self, field_obj):
        """Gets a string representing the Solr type, such as 'solr.TextField',
        then looks it up in solr_data_types to get back a sunburnt schema
        object, then maps that to a DRF serialization format.

        Still, this is better than having all fields explicitly laid out.
        """
        if field_obj.multi_valued:
            return serializers.ListField
        else:
            return self.solr_field_mappings[
                self.solr_data_types[
                    getattr(field_obj, 'class')
                ]
            ]
