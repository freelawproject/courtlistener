"""Factories used for testing functionality related to Texas state data."""

import random

from factory import DictFactory, Faker, List, SubFactory
from factory.declarations import LazyAttribute
from factory.django import DjangoModelFactory

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


class TexasTrialCourtDictFactory(DictFactory):
    # TODO Placeholder
    name = Faker("pystr")


class TexasCommonDataDictFactory(DictFactory):
    court_id = Faker(
        "random_element",
        elements=("texctapp1", "texctapp2", "tex", "texcrimapp"),
    )
    # Not correct, but close enough
    docket_number = Faker("federal_district_docket_number")
    case_name = Faker("case_name")
    case_name_full = Faker("case_name", full=True)
    date_filed = Faker("date_object")
    case_type = Faker("pystr")
    parties = List([SubFactory(TexasCasePartyDictFactory)])
    trial_court = SubFactory(TexasTrialCourtDictFactory)
    case_events = List([SubFactory(TexasDocketEntryDictFactory)])
    appellate_briefs = LazyAttribute(
        lambda d: filter(
            lambda e: True if random.random() < 0.1 else False, d.case_events
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
    document_url = Faker("url")

    class Meta:
        model = TexasDocument
