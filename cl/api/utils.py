from collections import OrderedDict

from django.utils.encoding import force_text
from rest_framework.metadata import SimpleMetadata


class NoChoicesMetadata(SimpleMetadata):
    """
    Don't include choices values for `OPTIONS` requests.

    See: https://github.com/tomchristie/django-rest-framework/issues/3751
    """

    def get_field_info(self, field):
        """
        Given an instance of a serializer field, return a dictionary
        of metadata about it.

        This is a simple override that removes the code that otherwise lists
        thousands or millions of choices in the 'choices' key of field_info.
        """
        field_info = OrderedDict()
        field_info['type'] = self.label_lookup[field]
        field_info['required'] = getattr(field, 'required', False)

        attrs = [
            'read_only', 'label', 'help_text',
            'min_length', 'max_length',
            'min_value', 'max_value'
        ]

        for attr in attrs:
            value = getattr(field, attr, None)
            if value is not None and value != '':
                field_info[attr] = force_text(value, strings_only=True)

        if getattr(field, 'child', None):
            field_info['child'] = self.get_field_info(field.child)
        elif getattr(field, 'fields', None):
            field_info['children'] = self.get_serializer_info(field)

        if not field_info.get('read_only') and hasattr(field, 'choices'):
            field_info['choices'] = "Too many values..."

        return field_info
