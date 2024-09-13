from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from cl.favorites.models import Note, Prayer, UserTag
from cl.search.factories import (
    OpinionClusterWithParentsFactory,
    RECAPDocumentFactory,
)
from cl.users.factories import UserWithChildProfileFactory


class NoteFactory(DjangoModelFactory):
    class Meta:
        model = Note

    user = SubFactory(UserWithChildProfileFactory)
    cluster_id = SubFactory(OpinionClusterWithParentsFactory)
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
