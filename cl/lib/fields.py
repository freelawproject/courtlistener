from django.db import models
from django_elasticsearch_dsl import fields
from elasticsearch_dsl import Percolator


class CharNullField(models.CharField):
    """
    Subclass of the CharField that allows empty strings to be stored as NULL.

    https://stackoverflow.com/a/1934764/64911
    """

    description = "CharField that stores NULL but returns ''."

    def from_db_value(self, value, expression, connection):
        """
        Gets value right out of the db and changes it if its ``None``.
        """
        if value is None:
            return ""
        else:
            return value

    def to_python(self, value):
        """
        Gets value right out of the db or an instance, and changes it if its ``None``.
        """
        if isinstance(value, models.CharField):
            # If an instance, just return the instance.
            return value
        if value is None:
            # If db has NULL, convert it to ''.
            return ""

        # Otherwise, just return the value.
        return value

    def get_prep_value(self, value):
        """
        Catches value right before sending to db.
        """
        if value == "":
            # If Django tries to save an empty string, send the db None (NULL).
            return None
        else:
            # Otherwise, just pass the value.
            return value


class PercolatorField(fields.DEDField, Percolator):
    """Subclass of DEDField and Percolator field.
    This subclass transforms the Percolator field into a field compatible with
    django_elasticsearch_dsl. This enables us to leverage DED Document methods
    like "prepare," which allows the field to be populated using the prepare
    method.
    """

    pass
