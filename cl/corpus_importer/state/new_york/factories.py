"""Factories for mocking the Court-PASS data the NYCoA mergers consume."""

from factory.base import Factory
from factory.declarations import (
    LazyAttribute,
    LazyFunction,
    List,
    Sequence,
    SubFactory,
)
from factory.faker import Faker
from juriscraper.state.docket import DocketEntryType, DocketType, PartyType
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    FilingDocType,
    FilingRole,
    classify_issue,
    filing_type_from_value,
)

from cl.corpus_importer.state.new_york.nycourts_gov import (
    NYCoAAttorney,
    NYCoACase,
    NYCoAFile,
    NYCoAIssue,
    NYCoAParty,
    NYCoDocketEntry,
)
from cl.corpus_importer.state.new_york.utils import NYCOA_COURT_ID
from cl.tests.providers import LegalProvider

Faker.add_provider(LegalProvider)


class NYCoAFileFactory(Factory):
    class Meta:
        model = NYCoAFile

    file_name = Sequence(lambda n: f"SmithvJones-app-Smith{n}-brf.pdf")
    content_type = "application/pdf"
    available = False
    doc_role = FilingRole.APPELLANT
    doc_party = "Smith"
    doc_type = FilingDocType.BRIEF
    local_path = Sequence(lambda n: f"/tmp/nycoa/{n}.pdf")


class NYCoAIssueFactory(Factory):
    """An issue as the scraper hands it over, already classified.

    The category and subcategory are classified off `category_raw` by the
    scraper's own classifier, so a test can state one string the way the Court
    does.
    """

    class Meta:
        model = NYCoAIssue

    category_raw = "Judgments--Confession of Judgment"
    category = LazyAttribute(lambda o: classify_issue(o.category_raw).category)
    subcategory = LazyAttribute(
        lambda o: classify_issue(o.category_raw).subcategory
    )
    detail = Faker("text", max_nb_chars=60)


class NYCoAFilingFactory(Factory):
    """A filing as the scraper hands it over, already classified.

    The classified filing type is read off `raw_filing_type` by the scraper's
    own classifier, which reports `None` both when no table row named the filing
    and when the table named a type the vocabulary does not cover. Which of the
    two it was, the schema decides off `raw_filing_type`; see
    `NYCoDocketEntry`.
    """

    class Meta:
        model = NYCoDocketEntry

    docket_entry_id = Sequence(lambda n: f"e:appellant-brief:smith{n}:1")
    entry_index = Sequence(lambda n: n)
    entry_type = DocketEntryType.BRIEF
    raw_filing_type = "Appellant Brief"
    entry_filing_type = LazyAttribute(
        lambda o: filing_type_from_value(o.raw_filing_type)
    )
    party = Faker("name")
    date_filed = Faker("date_object")
    date_due = Faker("date_object")
    entry_role = FilingRole.APPELLANT
    entry_doctype = FilingDocType.BRIEF
    attachments = LazyFunction(list)


class NYCoAAttorneyFactory(Factory):
    class Meta:
        model = NYCoAAttorney

    name = Faker("name")
    firm = Faker("company")
    address = Faker("address")
    # `Attorney.phone` is capped at 20 characters.
    phone = Faker("numerify", text="(###) ###-####")


class NYCoAPartyFactory(Factory):
    class Meta:
        model = NYCoAParty

    name = Faker("name")
    party_type = PartyType.APPELLANT
    party_role_raw = "Appellant"
    representatives = List([SubFactory(NYCoAAttorneyFactory)])


class NYCoACaseFactory(Factory):
    class Meta:
        model = NYCoACase

    court_id = NYCOA_COURT_ID
    docket_number = Sequence(lambda n: f"APL-2024-{n:05d}")
    case_name = Faker("case_name")
    case_name_full = Faker("case_name", full=True)
    case_name_short = Faker("case_name")
    docket_type = DocketType.UNKNOWN
    date_filed = Faker("date_object")
    argument_date = Faker("date_object")
    decision_date = None
    issues = List([SubFactory(NYCoAIssueFactory)])
    official_citation = ""
    lower_court_citation = "102 AD3d 543"
    transfers = LazyFunction(list)
    entries = LazyFunction(list)
    parties = LazyFunction(list)
