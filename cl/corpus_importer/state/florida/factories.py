"""Factories for mocking output of Florida Juriscraper modules."""

from datetime import UTC

from factory.base import Factory
from factory.declarations import LazyAttribute, List, SubFactory
from factory.faker import Faker
from juriscraper.state.docket import (
    DocketEntryType,
    DocketTransfer,
    TransferDirection,
    TransferReason,
)
from juriscraper.state.florida import FloridaPartyRepresentative
from juriscraper.state.florida.cases import (
    FLORIDA_DOCKET_TYPE_MAP,
    FloridaCase,
    FloridaOriginatingCase,
)
from juriscraper.state.florida.courts import FloridaCourtID
from juriscraper.state.florida.docket_entries import FloridaDocketEntry
from juriscraper.state.florida.documents import FloridaDocument
from juriscraper.state.florida.parties import FloridaParty, PartyType


class _PydanticConstructFactory(Factory):
    """Builds Pydantic models via ``model_construct`` so factories can use
    field names directly even though the upstream models declare
    ``validation_alias``\\es matching the Florida API payload shape."""

    class Meta:
        abstract = True

    @classmethod
    def _build(cls, model_class, *args, **kwargs):
        return model_class.model_construct(**kwargs)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return model_class.model_construct(**kwargs)


class FloridaOriginatingCaseFactory(_PydanticConstructFactory):
    class Meta:
        model = FloridaOriginatingCase

    court_name = Faker("court_name")
    court_id = Faker(
        "random_element",
        elements=(FloridaCourtID.CIRCUIT, FloridaCourtID.COUNTY),
    )
    case_number = Faker("federal_district_docket_number")


class FloridaDocketTransferFactory(_PydanticConstructFactory):
    class Meta:
        model = DocketTransfer

    direction = TransferDirection.INBOUND
    reason = TransferReason.APPEAL
    court_id = Faker(
        "random_element",
        elements=(
            FloridaCourtID.CIRCUIT.value,
            FloridaCourtID.COUNTY.value,
        ),
    )
    docket_number = Faker("federal_district_docket_number")


class FloridaRepresentativeFactory(_PydanticConstructFactory):
    class Meta:
        model = FloridaPartyRepresentative

    party_uuid = Faker("uuid4")
    name = Faker("name")
    sort_name = Faker("name")
    primary_flag = Faker("pybool")


class FloridaCasePartyFactory(_PydanticConstructFactory):
    class Meta:
        model = FloridaParty

    party_uuid = Faker("uuid4")
    party_type_raw = Faker("text")
    party_type = Faker("random_element", elements=PartyType)
    party_type_id = Faker("pyint")
    party_subtype = Faker("pystr")
    party_subtype_id = Faker("pyint")
    status = Faker("pystr")
    status_id = Faker("pyint")
    name = Faker("name")
    sort_name = Faker("name")
    pro_se_flag = Faker("pybool")
    order_by = Faker("pyint")
    representatives = List([SubFactory(FloridaRepresentativeFactory)])
    non_public_flag = Faker("pybool")
    party_number = Faker("pyint")
    involvement_type_id = Faker("pyint")


class FloridaDocumentFactory(_PydanticConstructFactory):
    class Meta:
        model = FloridaDocument

    docket_entry_uuid = Faker("uuid4")
    document_link_uuid = Faker("uuid4")
    document_name = Faker("text", max_nb_chars=50)
    user_document_state = Faker("uuid4")
    case_uuid = Faker("uuid4")
    case_number = Faker("federal_district_docket_number")
    case_title = Faker("case_name")
    court_id = Faker("pyint")
    document_type = Faker("pystr")
    content_type = "application/pdf"
    file_extension = "pdf"
    page_count = Faker("pyint", min_value=1, max_value=500)
    file_size = Faker("pyint", min_value=1000)
    url = Faker("url")


class FloridaDocketEntryFactory(_PydanticConstructFactory):
    class Meta:
        model = FloridaDocketEntry

    docket_entry_uuid = Faker("uuid4")
    datetime_filed = Faker("date_time", tzinfo=UTC)
    date_filed = LazyAttribute(lambda o: o.datetime_filed.date())
    date_submitted = Faker("date_time", tzinfo=UTC)
    entry_type = Faker("random_element", elements=DocketEntryType)
    entry_type_raw = Faker("text", max_nb_chars=20)
    entry_name = Faker("text", max_nb_chars=30)
    entry_status = Faker("pystr")
    entry_description = Faker("text")
    attachments = List([])


class FloridaCaseFactory(_PydanticConstructFactory):
    class Meta:
        model = FloridaCase

    case_uuid = Faker("uuid4")
    docket_number = Faker("federal_district_docket_number")
    case_name = Faker("case_name")
    case_name_full = Faker("case_name", full=True)
    case_name_short = Faker("case_name")
    case_caption = Faker("text")
    closed_flag = Faker("pybool")
    class_group_type = Faker("pystr")
    class_group_type_id = Faker("pyint")
    docket_type = Faker(
        "random_element", elements=list(FLORIDA_DOCKET_TYPE_MAP.values())
    )
    classification_id = Faker("pyint")
    court_id = Faker(
        "random_element",
        elements=(
            FloridaCourtID.FIRST_COA.value,
            FloridaCourtID.SECOND_COA.value,
            FloridaCourtID.SIXTH_COA.value,
            FloridaCourtID.SUPREME_COURT.value,
        ),
    )
    court_abbreviation = Faker("pystr", max_chars=3)
    location = Faker("city")
    location_id = Faker("pyint")
    datetime_filed = Faker("date_time")
    date_filed = LazyAttribute(lambda o: o.datetime_filed.date())
    case_group_flag = Faker("pybool")
    panel_flag = Faker("pybool")
    originating_cases = List([SubFactory(FloridaOriginatingCaseFactory)])
    transfers = List([SubFactory(FloridaDocketTransferFactory)])
    entries = List([SubFactory(FloridaDocketEntryFactory)])
    parties = List([SubFactory(FloridaCasePartyFactory)])
