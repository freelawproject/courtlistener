import copy
import datetime
from collections import OrderedDict

from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from django_elasticsearch_dsl import Document, fields
from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.utils.field_mapping import get_field_kwargs

from cl.custom_filters.templatetags.extras import render_string_or_list


class TimeStampField(serializers.Field):
    """Handles a naive timestamp field."""

    def __init__(self, default_timezone=None, **kwargs):
        self.timezone = None
        if default_timezone is not None:
            self.timezone = default_timezone
        super().__init__(**kwargs)

    def to_representation(self, value):
        if isinstance(value, datetime.datetime) and timezone.is_naive(value):
            if self.timezone:
                return serializers.DateTimeField(
                    default_timezone=self.timezone
                ).to_representation(value)
            else:
                date_time_aware = timezone.make_aware(
                    value, datetime.timezone.utc
                )
                return serializers.DateTimeField().to_representation(
                    timezone.localtime(date_time_aware)
                )
        if isinstance(value, str):
            try:
                format_string = "%Y-%m-%dT%H:%M:%S.%f"
                parsed_datetime = datetime.datetime.strptime(
                    value, format_string
                )
            except ValueError:
                # If the above format fails, try parsing with timezone
                # information
                format_string = "%Y-%m-%dT%H:%M:%S.%f%z"
                parsed_datetime = datetime.datetime.strptime(
                    value, format_string
                )
            return serializers.DateTimeField(
                default_timezone=self.timezone
            ).to_representation(parsed_datetime)
        else:
            raise serializers.ValidationError(
                "Date or DateTime object expected."
            )


class DateOrDateTimeField(serializers.Field):
    """Handles both datetime and date objects."""

    def to_representation(self, value):
        if isinstance(value, datetime.datetime):
            return serializers.DateTimeField().to_representation(value)
        elif isinstance(value, datetime.date):
            return serializers.DateField().to_representation(value)
        else:
            return value


class DateField(serializers.Field):
    """Handles date objects."""

    def to_representation(self, value):
        if isinstance(value, datetime.datetime):
            return serializers.DateField().to_representation(value.date())
        else:
            return serializers.DateField().to_representation(value)


class NullableListField(serializers.ListField):
    """A custom ListField that returns None when serialized if the list is
    empty. For API V3 compatibility.
    """

    def to_representation(self, data):
        """
        Return "None" if the list is empty, otherwise return the list.
        """
        if not data:
            return None
        return super().to_representation(data)


class HighlightedField(serializers.Field):
    """Handles highlighted text fields."""

    def to_representation(self, value):
        return render_string_or_list(value)


class DocumentSerializer(serializers.Serializer):
    """A dynamic DocumentSerializer class."""

    def update(self, instance, validated_data):
        raise NotImplementedError

    def create(self, validated_data):
        raise NotImplementedError

    _field_mapping = {
        fields.BooleanField: serializers.BooleanField,
        fields.ByteField: serializers.CharField,
        fields.CompletionField: serializers.CharField,
        fields.DateField: DateOrDateTimeField,
        fields.DoubleField: serializers.FloatField,
        fields.FloatField: serializers.FloatField,
        fields.IntegerField: serializers.IntegerField,
        fields.IpField: serializers.IPAddressField,
        fields.LongField: serializers.IntegerField,
        fields.ShortField: serializers.IntegerField,
        fields.KeywordField: serializers.CharField,
        fields.TextField: serializers.CharField,
    }

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance, data, **kwargs)

        if not hasattr(self, "Meta"):
            raise ImproperlyConfigured(
                f'Class {self.__class__.__name__} missing "Meta" attribute'
            )

        if not hasattr(self.Meta, "document") or self.Meta.document is None:
            raise ImproperlyConfigured(
                "You must set the 'document' attribute on the serializer "
                "Meta class."
            )

        if not issubclass(self.Meta.document, (Document,)):
            raise ImproperlyConfigured(
                "You must subclass the serializer 'document' from the Document"
                "class."
            )

    @staticmethod
    def _get_default_field_kwargs(model, field_name, field_type):
        """Get default field kwargs.

        Get the required attributes from the model field in order
        to instantiate a REST Framework serializer field.
        """
        kwargs = {}
        if field_name in model._meta.get_fields():
            model_field = model._meta.get_field(field_type)[0]
            kwargs = get_field_kwargs(field_name, model_field)

            # Remove stuff we don't care about!
            delete_attrs = [
                "allow_blank",
                "choices",
                "model_field",
            ]
            for attr in delete_attrs:
                if attr in kwargs:
                    del kwargs[attr]

        return kwargs

    def get_fields(self):
        """Get the required fields for serializing the result."""
        fields = getattr(self.Meta, "fields", ())
        exclude = getattr(self.Meta, "exclude", ())
        ignore_fields = getattr(self.Meta, "ignore_fields", ())
        document = getattr(self.Meta, "document")
        model = document.Django.model
        document_fields = document._fields
        declared_fields = copy.deepcopy(self._declared_fields)
        field_mapping = OrderedDict()

        if all([fields, exclude]):
            raise ImproperlyConfigured(
                "Cannot set both 'fields' and 'exclude' options on "
                f"serializer {self.__class__.__name__}."
            )

        if not any([fields, exclude]):
            raise ImproperlyConfigured(
                "Creating a serializer without either the 'fields' attribute "
                "or the 'exclude' attribute is not allowed, Add an explicit "
                f"fields = '__all__' to the {self.__class__.__name__} serializer."
            )

        # Match drf convention of specifying "__all__" for all available fields
        # This is the existing behavior so we can ignore this value.
        if fields == "__all__":
            fields = ()

        for field_name, field_type in document_fields.items():
            # Don't use this field if it is in `ignore_fields`
            if field_name in ignore_fields:
                continue
            # When fields to include are decided by `exclude`
            if exclude and field_name in exclude:
                continue
            # When fields to include are decided by `fields`
            if fields and field_name not in fields:
                continue

            # Look up the field attributes on the current index model,
            # in order to correctly instantiate the serializer field.

            kwargs = self._get_default_field_kwargs(
                model, field_name, field_type
            )
            # If field not in the mapping, just skip
            if field_type.__class__ not in self._field_mapping:
                continue

            # check whether the field can contain array of values
            if field_type._multi:
                field_mapping[field_name] = serializers.ListField(**kwargs)
            else:
                field_mapping[field_name] = self._field_mapping[
                    field_type.__class__
                ](**kwargs)

        # Add any explicitly declared fields. They *will* override any index
        # fields in case of naming collision!.
        if declared_fields:
            for field_name in declared_fields:
                field_mapping[field_name] = declared_fields[field_name]

        field_mapping = OrderedDict(sorted(field_mapping.items()))
        return field_mapping
