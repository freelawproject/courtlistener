from django.contrib.contenttypes.models import ContentType
from factory import Faker, LazyAttribute, SelfAttribute, SubFactory
from factory.django import DjangoModelFactory

from cl.favorites.models import Note, Prayer, UserTag
from cl.search.factories import (
    OpinionClusterWithParentsFactory,
    RECAPDocumentFactory,
)
from cl.users.factories import UserWithChildProfileFactory


class NoteFactory(DjangoModelFactory):
    """Builds a Note on an OpinionCluster by default. Pass content_object=
    to attach it to any other saved noteable object instead (see
    NOTEABLE_MODELS in cl/favorites/utils.py).
    """

    class Meta:
        model = Note
        exclude = ("content_object",)

    user = SubFactory(UserWithChildProfileFactory)
    content_object = SubFactory(OpinionClusterWithParentsFactory)
    content_type = LazyAttribute(
        lambda o: ContentType.objects.get_for_model(o.content_object)
    )
    object_id = SelfAttribute("content_object.pk")
    name = Faker("text", max_nb_chars=20)
    notes = Faker("text", max_nb_chars=50)


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
