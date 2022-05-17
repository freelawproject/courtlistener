from factory import SubFactory
from factory.django import DjangoModelFactory, FileField
from factory.fuzzy import FuzzyChoice

from cl.recap.constants import DATASET_SOURCES
from cl.recap.models import FjcIntegratedDatabase, ProcessingQueue
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

    filepath_local = FileField(filename=None)
