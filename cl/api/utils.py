from rest_framework import serializers

DATETIME_LOOKUPS = ['exact', 'gte', 'gt', 'lte', 'lt', 'range', 'year',
                    'month', 'day', 'hour', 'minute', 'second']
DATE_LOOKUPS = DATETIME_LOOKUPS[:-3]
INTEGER_LOOKUPS = ['exact', 'gte', 'gt', 'lte', 'lt', 'range']
BASIC_TEXT_LOOKUPS = ['exact', 'iexact', 'startswith', 'istartswith',
                      'endswith', 'iendswith']
ALL_TEXT_LOOKUPS = BASIC_TEXT_LOOKUPS + ['contains', 'icontains']


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    A ModelSerializer that takes an additional `fields` argument that
    controls which fields should be displayed.
    """

    def __init__(self, *args, **kwargs):
        # Instantiate the superclass normally
        super(DynamicFieldsModelSerializer, self).__init__(*args, **kwargs)
        if not self.context or not self.context.get('request'):
            # This happens during initialization.
            return
        fields = self.context['request'].query_params.get('fields')
        if fields is not None:
            fields = fields.split(',')
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields.keys())
            for field_name in existing - allowed:
                self.fields.pop(field_name)
