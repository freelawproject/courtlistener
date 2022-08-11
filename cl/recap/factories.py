from factory import Faker, SubFactory
from factory.django import DjangoModelFactory, FileField
from factory.fuzzy import FuzzyChoice

from cl.recap.constants import DATASET_SOURCES
from cl.recap.models import UPLOAD_TYPE, FjcIntegratedDatabase, ProcessingQueue
from cl.search.factories import CourtFactory


class FjcIntegratedDatabaseFactory(DjangoModelFactory):
    class Meta:
        model = FjcIntegratedDatabase

    dataset_source = FuzzyChoice(DATASET_SOURCES, getter=lambda c: c[0])
    circuit = SubFactory(CourtFactory)
    district = SubFactory(CourtFactory)


class ProcessingQueueFactory(DjangoModelFactory):
    class Meta:
        model = ProcessingQueue

    pacer_case_id = Faker("pyint", min_value=100_000, max_value=400_000)
    upload_type = FuzzyChoice(UPLOAD_TYPE.NAMES, getter=lambda c: c[0])
    filepath_local = FileField(filename=None)
