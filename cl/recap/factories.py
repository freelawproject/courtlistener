import string

from factory import DictFactory, Faker, List, SubFactory
from factory.django import DjangoModelFactory, FileField
from factory.fuzzy import FuzzyChoice, FuzzyFloat, FuzzyInteger, FuzzyText

from cl.recap.constants import DATASET_SOURCES
from cl.recap.models import (
    REQUEST_TYPE,
    UPLOAD_TYPE,
    FjcIntegratedDatabase,
    PacerFetchQueue,
    ProcessingQueue,
)
from cl.search.factories import CourtFactory
from cl.tests.providers import LegalProvider

Faker.add_provider(LegalProvider)


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
    filepath_local = FileField(filename="document.html")


class PacerFetchQueueFactory(DjangoModelFactory):
    class Meta:
        model = PacerFetchQueue

    pacer_case_id = Faker("pyint", min_value=100_000, max_value=400_000)
    request_type = FuzzyChoice(REQUEST_TYPE.NAMES, getter=lambda c: c[0])


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


class ACMSAttachmentFactory(AppellateAttachmentFactory):
    acms_document_guid = Faker("random_id_string")
    cost = FuzzyFloat(0.1, 3.0)
    permission = Faker("text", max_nb_chars=20)
    file_size = FuzzyInteger(100)
    date_filed = Faker("date_object")


class ACMSAttachmentPageFactory(AppellateAttachmentPageFactory):
    entry_number = Faker("pyint", min_value=0, max_value=100)
    description = Faker("text", max_nb_chars=20)
    date_filed = Faker("date_object")
    date_end = Faker("date_object")


class DocketEntryDataFactory(DictFactory):
    date_filed = Faker("date_object")
    description = Faker("text", max_nb_chars=75)
    document_number = Faker("pyint", min_value=1, max_value=100)
    pacer_doc_id = Faker("pyint", min_value=100_000, max_value=400_000)


class DocketEntriesDataFactory(DictFactory):
    docket_entries = List([SubFactory(DocketEntryDataFactory)])


class RECAPEmailDocketEntryDataFactory(DictFactory):
    date_filed = Faker("date_object")
    description = Faker("text", max_nb_chars=75)
    document_number = Faker("pyint", min_value=1, max_value=100)
    document_url = Faker("url")
    pacer_case_id = Faker("random_id_string")
    pacer_doc_id = Faker("random_id_string")
    pacer_magic_num = Faker("random_id_string")
    pacer_seq_no = Faker("random_id_string")
    short_description = Faker("text", max_nb_chars=15)


class RECAPEmailDocketDataFactory(DictFactory):
    case_name = Faker("case_name")
    date_filed = Faker("date_object")
    docket_entries = List([SubFactory(RECAPEmailDocketEntryDataFactory)])
    docket_number = Faker("federal_district_docket_number")


class RECAPEmailRecipientsDataFactory(DictFactory):
    email_addresses = List([Faker("email")])
    name = Faker("name_female")


class RECAPEmailNotificationDataFactory(DictFactory):
    appellate = Faker("boolean")
    contains_attachments = Faker("boolean")
    court_id = FuzzyText(length=4, chars=string.ascii_lowercase, suffix="d")
    dockets = List([SubFactory(RECAPEmailDocketDataFactory)])
    email_recipients = List([SubFactory(RECAPEmailRecipientsDataFactory)])


class MinuteDocketEntryDataFactory(DictFactory):
    date_entered = Faker("date_object")
    date_filed = Faker("date_object")
    description = Faker("text", max_nb_chars=75)
    document_number = None
    pacer_doc_id = None
    pacer_seq_no = None
    short_description = Faker("text", max_nb_chars=30)


class DocketDataFactory(DictFactory):
    court_id = FuzzyText(length=4, chars=string.ascii_lowercase, suffix="d")
    case_name = Faker("case_name")
    docket_entries = List([SubFactory(MinuteDocketEntryDataFactory)])
    docket_number = Faker("federal_district_docket_number")
    date_filed = Faker("date_object")
    ordered_by = "date_filed"
    federal_dn_office_code = Faker("pyint", min_value=1, max_value=10)
    federal_dn_case_type = FuzzyText(length=2, chars=string.ascii_lowercase)
    federal_dn_judge_initials_assigned = FuzzyText(
        length=5, chars=string.ascii_lowercase
    )
    federal_dn_judge_initials_referred = FuzzyText(
        length=5, chars=string.ascii_lowercase
    )
    federal_defendant_number = Faker("pyint", min_value=1, max_value=999)


class DocketWithBankruptcyDataFactory(DictFactory):
    court_id = FuzzyText(length=4, chars=string.ascii_lowercase, suffix="d")
    case_name = Faker("case_name")
    docket_number = Faker("federal_district_docket_number")
    date_filed = Faker("date_object")
    ordered_by = "date_filed"
    chapter = Faker("pyint", min_value=1, max_value=100)
    trustee_str = Faker("text", max_nb_chars=15)


class DocketEntryWithAttachmentsDataFactory(MinuteDocketEntryDataFactory):
    attachments = List([SubFactory(AppellateAttachmentPageFactory)])


class DocketDataWithAttachmentsFactory(DocketDataFactory):
    docket_entries = List([SubFactory(DocketEntryWithAttachmentsDataFactory)])


class OriginatingCourtInformationDataFactory(DictFactory):
    assigned_to = Faker("name")
    court_id = FuzzyText(length=4, chars=string.ascii_lowercase, suffix="d")
    ordering_judge = Faker("name")
