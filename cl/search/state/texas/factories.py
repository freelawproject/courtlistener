"""Factories used for testing functionality related to Texas state data."""

import random

from factory import DictFactory, Faker, List, SubFactory
from factory.declarations import LazyAttribute
from factory.django import DjangoModelFactory
from juriscraper.state.texas.common import CourtID, CourtType

from cl.search.factories import DocketFactory
from cl.search.models import TexasDocketEntry, TexasDocument


class TexasCaseDocumentDictFactory(DictFactory):
    document_url = Faker("url")
    media_id = Faker("uuid4")
    media_version_id = Faker("uuid4")
    description = Faker("text")
    file_size_bytes = Faker("pyint")
    file_size_str = Faker("pystr")


class TexasDocketEntryDictFactory(DictFactory):
    date = Faker("date_object")
    type = Faker("pystr", min_chars=3, max_chars=3)
    disposition = Faker("text")
    description = Faker("text")
    remarks = Faker("text")
    attachments = List([SubFactory(TexasCaseDocumentDictFactory)])


class TexasCasePartyDictFactory(DictFactory):
    name = Faker("name")
    type = Faker("pystr")
    representatives = List([Faker("name")])


class TexasOriginatingCourtDictFactory(DictFactory):
    name = Faker("court_name")
    court_type = Faker(
        "random_element",
        elements=(
            CourtType.PROBATE.value,
            CourtType.BUSINESS.value,
            CourtType.COUNTY.value,
            CourtType.MUNICIPAL.value,
            CourtType.JUSTICE.value,
            CourtType.UNKNOWN.value,
        ),
    )
    county = Faker("pystr")
    judge = Faker("name")
    # Close enough for testing
    case = Faker("federal_district_docket_number")
    reporter = Faker("name")
    punishment = Faker("pystr")


class TexasOriginatingAppellateCourtDictFactory(
    TexasOriginatingCourtDictFactory
):
    court_type = CourtType.APPELLATE.value
    court_id = Faker(
        "random_element",
        elements=(
            CourtID.FIRST_COURT_OF_APPEALS.value,
            CourtID.SECOND_COURT_OF_APPEALS.value,
            CourtID.FOURTEENTH_COURT_OF_APPEALS.value,
            CourtID.FIFTEENTH_COURT_OF_APPEALS.value,
        ),
    )


class TexasOriginatingDistrictCourtDictFactory(
    TexasOriginatingCourtDictFactory
):
    court_type = CourtType.DISTRICT.value
    district = Faker("random_element", elements=list(range(1, 527)) + [None])


class TexasCommonDataDictFactory(DictFactory):
    court_id = Faker(
        "random_element",
        elements=(
            CourtID.FIRST_COURT_OF_APPEALS.value,
            CourtID.SECOND_COURT_OF_APPEALS.value,
            CourtID.SUPREME_COURT.value,
            CourtID.COURT_OF_CRIMINAL_APPEALS.value,
        ),
    )
    court_type = Faker(
        "random_element",
        elements=("texas_appellate", "texas_final"),
    )
    # Not correct, but close enough
    docket_number = Faker("federal_district_docket_number")
    case_name = Faker("case_name")
    case_name_full = Faker("case_name", full=True)
    date_filed = Faker("date_object")
    case_type = Faker("pystr")
    parties = List([SubFactory(TexasCasePartyDictFactory)])
    originating_court = SubFactory(TexasOriginatingCourtDictFactory)
    case_events = List([SubFactory(TexasDocketEntryDictFactory)])
    appellate_briefs = LazyAttribute(
        lambda d: list(
            filter(
                lambda e: True if random.random() < 0.1 else False,
                d.case_events,
            )
        )
    )


class TexasDocketEntryFactory(DjangoModelFactory):
    docket = SubFactory(DocketFactory)
    appellate_brief = Faker("pybool", truth_probability=10)
    description = Faker("text", max_nb_chars=25)
    remarks = Faker("text", max_nb_chars=25)
    disposition = Faker("text", max_nb_chars=25)
    date_filed = Faker("date_object")
    entry_type = Faker("pystr", min_chars=3, max_chars=3)
    sequence_number = LazyAttribute(
        lambda self: f"{self.date_filed.isoformat()}.{random.randint(1, 3)}"
    )

    class Meta:
        model = TexasDocketEntry


class TexasDocumentFactory(DjangoModelFactory):
    docket_entry = SubFactory(TexasDocketEntryFactory)
    description = Faker("text", max_nb_chars=25)
    media_id = Faker("uuid4")
    media_version_id = Faker("uuid4")
    url = Faker("url")

    class Meta:
        model = TexasDocument


class TexasAppellateCourtInfoDictFactory(DictFactory):
    """Factory for appeals_court field in Texas final court dockets."""

    court_id = Faker(
        "random_element",
        elements=(
            CourtID.FIRST_COURT_OF_APPEALS.value,
            CourtID.SECOND_COURT_OF_APPEALS.value,
            CourtID.FOURTEENTH_COURT_OF_APPEALS.value,
            CourtID.UNKNOWN.value,
        ),
    )
    case_number = Faker("federal_district_docket_number")
    case_url = Faker("url")
    disposition = Faker("pystr")
    district = Faker("pystr")
    justice = Faker("name")
    opinion_cite = Faker("citation")


class TexasAppellateTransferDictFactory(DictFactory):
    """Factory for transfer_from field in Texas appellate dockets."""

    court_id = Faker(
        "random_element",
        elements=(
            CourtID.FIRST_COURT_OF_APPEALS.value,
            CourtID.SECOND_COURT_OF_APPEALS.value,
            CourtID.FOURTEENTH_COURT_OF_APPEALS.value,
        ),
    )
    origin_docket = Faker("federal_district_docket_number")
    date = Faker("date_object")


class TexasCourtOfAppealsDocketDictFactory(TexasCommonDataDictFactory):
    """Factory for Texas Court of Appeals docket data."""

    court_type = "texas_appellate"
    court_id = Faker(
        "random_element",
        elements=(
            CourtID.FIRST_COURT_OF_APPEALS.value,
            CourtID.SECOND_COURT_OF_APPEALS.value,
            CourtID.FOURTEENTH_COURT_OF_APPEALS.value,
        ),
    )
    transfer_from = LazyAttribute(
        lambda d: TexasAppellateTransferDictFactory.create()
        if random.random() < 0.1
        else None
    )
    transfer_to = LazyAttribute(
        lambda d: TexasAppellateTransferDictFactory.create()
        if random.random() < 0.1
        else None
    )


class TexasFinalCourtDocketDictFactory(TexasCommonDataDictFactory):
    """Factory for Texas Supreme Court and Court of Criminal Appeals docket data."""

    court_type = "texas_final"
    appeals_court = SubFactory(TexasAppellateCourtInfoDictFactory)
    court_id = Faker(
        "random_element",
        elements=(
            CourtID.SUPREME_COURT.value,
            CourtID.COURT_OF_CRIMINAL_APPEALS.value,
        ),
    )
