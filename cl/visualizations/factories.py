from factory import Faker, RelatedFactory, SubFactory
from factory.django import DjangoModelFactory

from cl.search.factories import OpinionClusterWithParentsFactory
from cl.users.factories import UserWithChildProfileFactory
from cl.visualizations.models import JSONVersion, SCOTUSMap


class VisualizationFactory(DjangoModelFactory):
    class Meta:
        model = SCOTUSMap

    user = SubFactory(UserWithChildProfileFactory)
    cluster_start = SubFactory(OpinionClusterWithParentsFactory)
    cluster_end = SubFactory(OpinionClusterWithParentsFactory)
    title = Faker("text", max_nb_chars=20)
    slug = Faker("slug")
    view_count = Faker("random_int")
    published = Faker("boolean")
    deleted = Faker("boolean")
    generation_time = Faker("random_int")
    notes = Faker("text", max_nb_chars=50)
    json_versions = RelatedFactory(
        "cl.visualizations.factories.JSONVersionFactory",
        factory_related_name="map",
    )


class JSONVersionFactory(DjangoModelFactory):
    class Meta:
        model = JSONVersion
