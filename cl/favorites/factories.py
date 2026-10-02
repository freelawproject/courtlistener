from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from cl.favorites.models import Note, Prayer, UserTag
from cl.search.factories import (
    OpinionClusterWithParentsFactory,
    RECAPDocumentFactory,
)
from cl.users.factories import UserWithChildProfileFactory


class NoteFactory(DjangoModelFactory):
    """Builds a Note in the legacy per-type-FK shape (cluster_id set) by
    default -- still valid since #7725 keeps the legacy fields, and useful
    for testing the dual-read fallback path. Use for_object() below for
    the new GenericForeignKey shape instead.
    """

    class Meta:
        model = Note

    user = SubFactory(UserWithChildProfileFactory)
    cluster_id = SubFactory(OpinionClusterWithParentsFactory)
    name = Faker("text", max_nb_chars=20)
    notes = Faker("text", max_nb_chars=50)

    @classmethod
    def for_object(cls, obj: Model, **kwargs) -> Note:
        """Build a Note in the new GenericForeignKey shape, attached to a
        saved noteable object (see NOTEABLE_MODELS in cl/favorites/utils.py).

        :param obj: A saved model instance to attach the Note to.
        :param kwargs: Extra NoteFactory fields, e.g. user=... or notes=...
        :return: The created Note.
        """
        content_type = ContentType.objects.get_for_model(type(obj))
        return cls.create(
            cluster_id=None,
            content_type=content_type,
            object_id=obj.pk,
            **kwargs,
        )


class UserTagFactory(DjangoModelFactory):
    class Meta:
        model = UserTag


class PrayerFactory(DjangoModelFactory):
    class Meta:
        model = Prayer

    date_created = Faker("date_time_this_year")
    user = SubFactory(UserWithChildProfileFactory)
    recap_document = SubFactory(RECAPDocumentFactory)
    status = Faker("random_element", elements=[Prayer.WAITING, Prayer.GRANTED])
