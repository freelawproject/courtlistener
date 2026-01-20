import random

from factory import DictFactory, Faker, List, SubFactory
from factory.declarations import LazyAttribute


class TexasCaseDocumentFactory(DictFactory):
    document_url = Faker("url")
    media_id = Faker("uuid4")
    media_version_id = Faker("uuid4")
    description = Faker("text")
    file_size_bytes = Faker("pyint")
    file_size_str = Faker("pystr")


class TexasDocketEntryFactory(DictFactory):
    date = Faker("date_object")
    type = Faker("pystr", min_chars=3, max_chars=3)
    disposition = Faker("text")
    description = Faker("text")
    remarks = Faker("text")
    attachments = List([SubFactory(TexasCaseDocumentFactory)])


class TexasCasePartyFactory(DictFactory):
    name = Faker("name")
    type = Faker("pystr")
    representatives = List([Faker("name")])


class TexasTrialCourtFactory(DictFactory):
    # TODO Placeholder
    name = Faker("pystr")


class TexasCommonDataFactory(DictFactory):
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
    parties = List([SubFactory(TexasCasePartyFactory)])
    trial_court = SubFactory(TexasTrialCourtFactory)
    case_events = List([SubFactory(TexasDocketEntryFactory)])
    appellate_briefs = LazyAttribute(
        lambda d: filter(
            lambda e: True if random.random() < 0.1 else False, d.case_events
        )
    )
