from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from cl.favorites.models import Favorite, UserTag
from cl.search.factories import OpinionClusterWithParentsFactory
from cl.users.factories import UserWithChildProfileFactory


class FavoriteFactory(DjangoModelFactory):
    class Meta:
        model = Favorite

    user = SubFactory(UserWithChildProfileFactory)
    cluster_id = SubFactory(OpinionClusterWithParentsFactory)
    name = Faker("text", max_nb_chars=20)
    notes = Faker("text", max_nb_chars=50)


class UserTagFactory(DjangoModelFactory):
    class Meta:
        model = UserTag
