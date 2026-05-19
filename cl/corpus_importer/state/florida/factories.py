"""Factories for mocking output of Florida Juriscraper modules."""

from datetime import date

from factory.declarations import List, SubFactory
from faker import Factory, Faker
from juriscraper.state.florida.cases import FLORIDA_DOCKET_TYPE_MAP
from juriscraper.state.florida.courts import FloridaCourtID


# These remain empty for now as they're not relevant to this merger.
class FloridaOriginatingCaseFactory(Factory): ...


class FloridaDocketTransferFactory(Factory): ...


class FloridaCasePartyFactory(Factory): ...


class FloridaDocketEntryFactory(Factory): ...


class FloridaCaseFactory(Factory):
    case_uuid = Faker("uuid4")
    docket_number = Faker("federal_district_docket_number")
    case_name = Faker("case_name")
    case_name_full = Faker("case_name", full=True)
    case_caption = Faker("text")
    closed_flag = Faker("pybool")
    class_group_type = Faker("pystr")
    class_group_type_id = Faker("pyint")
    docket_type = Faker(
        "random_element", elements=FLORIDA_DOCKET_TYPE_MAP.values()
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
    case_group_flag = Faker("pybool")
    panel_flag = Faker("pybool")
    originating_cases = List([SubFactory(FloridaOriginatingCaseFactory)])
    transfers = List([SubFactory(FloridaDocketTransferFactory)])
    entries = List([SubFactory(FloridaDocketEntryFactory)])
    parties = List([SubFactory(FloridaCasePartyFactory)])

    @property
    def date_filed(self) -> date:
        return self.datetime_filed.date()
