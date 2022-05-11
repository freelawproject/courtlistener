from factory import SubFactory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.recap.constants import DATASET_SOURCES
from cl.recap.models import FjcIntegratedDatabase, ProcessingQueue
from cl.search.models import Court


class FjcIntegratedDatabaseFactory(DjangoModelFactory):
    class Meta:
        model = FjcIntegratedDatabase

    dataset_source = FuzzyChoice(DATASET_SOURCES, getter=lambda c: c[0])
    circuit = SubFactory(Court)
    district = SubFactory(Court)


class ProcessingQueueFactory(DjangoModelFactory):
    class Meta:
        model = ProcessingQueue
