"""Factories for mocking output of Florida Juriscraper modules."""

from factory.base import Factory
from factory.declarations import LazyAttribute, List, SubFactory
from factory.faker import Faker
from juriscraper.state.docket import DocketTransfer
from juriscraper.state.florida import FloridaPartyRepresentative
from juriscraper.state.florida.cases import (
    FLORIDA_DOCKET_TYPE_MAP,
    FloridaCase,
    FloridaOriginatingCase,
)
from juriscraper.state.florida.courts import FloridaCourtID
from juriscraper.state.florida.docket_entries import FloridaDocketEntry
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


# The merger does not currently read fields off these objects, so the factories
# just produce stubs.
class FloridaDocketTransferFactory(_PydanticConstructFactory):
    class Meta:
        model = DocketTransfer


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


class FloridaDocketEntryFactory(_PydanticConstructFactory):
    class Meta:
        model = FloridaDocketEntry

    date_filed = Faker("date_object")


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
