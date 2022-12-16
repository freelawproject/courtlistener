from factory import DictFactory, Faker, List, SubFactory
from factory.django import DjangoModelFactory, FileField
from factory.fuzzy import FuzzyChoice, FuzzyInteger

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


class AppellateAttachmentFactory(DictFactory):
    attachment_number = Faker("pyint", min_value=1, max_value=100)
    description = Faker("text", max_nb_chars=20)
    pacer_doc_id = Faker("pyint", min_value=100_000, max_value=400_000)
    page_count = FuzzyInteger(100)


class AppellateAttachmentPageFactory(DictFactory):
    attachments = List([SubFactory(AppellateAttachmentFactory)])
    pacer_case_id = Faker("pyint", min_value=100_000, max_value=400_000)
    pacer_doc_id = Faker("pyint", min_value=100_000, max_value=400_000)
    pacer_seq_no = Faker("pyint", min_value=10_000, max_value=200_000)


class DocketEntryDataFactory(DictFactory):
    date_filed = Faker("date_object")
    description = Faker("text", max_nb_chars=75)
    document_number = Faker("pyint", min_value=1, max_value=100)
    pacer_doc_id = Faker("pyint", min_value=100_000, max_value=400_000)


class DocketEntriesDataFactory(DictFactory):
    docket_entries = List([SubFactory(DocketEntryDataFactory)])
