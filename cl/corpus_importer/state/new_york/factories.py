"""Factories for mocking the Court-PASS data the NYCoA mergers consume."""

from typing import NamedTuple

from factory.base import Factory
from factory.declarations import (
    LazyAttribute,
    LazyAttributeSequence,
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
    FilingType,
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
from cl.corpus_importer.state.new_york.storage import PRIVATE_PREFIX
from cl.corpus_importer.state.new_york.utils import NYCOA_COURT_ID
from cl.tests.providers import LegalProvider

Faker.add_provider(LegalProvider)


class _Filing(NamedTuple):
    """One kind of filing, with everything the FILINGS table implies about it.

    The scraper reads a filing's role and document type off its filing type, so
    a factory drawing the three independently would state filings that
    contradict themselves -- an amicus brief filed by the appellant. Pairing
    them here keeps a randomly chosen filing a coherent one. Juriscraper's own
    `FILING_TYPE_MAP` is not part of its published API, hence the handful
    repeated here.

    :ivar filing_type: The filing type, whose value is the Court's own wording.
    :ivar role: The party role the filing type implies.
    :ivar doctype: The document type the filing type implies.
    :ivar entry_type: The standard docket entry type for the filing.
    """

    filing_type: FilingType
    role: FilingRole
    doctype: FilingDocType
    entry_type: DocketEntryType


_FILINGS: tuple[_Filing, ...] = (
    _Filing(
        FilingType.APPELLANT_BRIEF,
        FilingRole.APPELLANT,
        FilingDocType.BRIEF,
        DocketEntryType.BRIEF,
    ),
    _Filing(
        FilingType.APPELLANT_REPLY_BRIEF,
        FilingRole.APPELLANT,
        FilingDocType.REPLY_BRIEF,
        DocketEntryType.BRIEF,
    ),
    _Filing(
        FilingType.RESPONDENT_BRIEF,
        FilingRole.RESPONDENT,
        FilingDocType.BRIEF,
        DocketEntryType.BRIEF,
    ),
    _Filing(
        FilingType.PETITIONER_BRIEF,
        FilingRole.PETITIONER,
        FilingDocType.BRIEF,
        DocketEntryType.BRIEF,
    ),
    _Filing(
        FilingType.AMICUS_BRIEF,
        FilingRole.AMICUS,
        FilingDocType.AMICUS_BRIEF,
        DocketEntryType.BRIEF,
    ),
    _Filing(
        FilingType.APPELLANT_SSM_LETTER,
        FilingRole.APPELLANT,
        FilingDocType.SSM_LETTER,
        DocketEntryType.LETTER,
    ),
)


class _PartyRole(NamedTuple):
    """A party role Court-PASS states, with the standard type it maps to.

    :ivar raw: The role exactly as the ATTORNEY DETAILS section states it.
    :ivar party_type: The standard party type the role maps to.
    """

    raw: str
    party_type: PartyType


_PARTY_ROLES: tuple[_PartyRole, ...] = (
    _PartyRole("Appellant", PartyType.APPELLANT),
    _PartyRole("Respondent", PartyType.RESPONDENT),
    _PartyRole("Petitioner", PartyType.PETITIONER),
    # The standard vocabulary has no amicus member, so an amicus keeps the
    # Court's own wording on `party_role_raw` and reads as unassigned.
    _PartyRole("Amicus Curiae", PartyType.UNASSIGNED),
)

# Issues the Court has stated, each a category and a subcategory joined by the
# double dash it writes them with. Every one is covered by the scraper's
# vocabularies, so the classified fields below come back set; a test wanting
# the uncovered case states `category_raw` itself.
_ISSUES: tuple[str, ...] = (
    "Contracts--Breach or Performance of Contract",
    "Crimes--Sentence",
    "Insurance--Coverage",
    "Judgments--Confession of Judgment",
    "Municipal Corporations--Zoning",
    "Negligence--Duty",
)


class NYCoAFileFactory(Factory):
    class Meta:
        model = NYCoAFile

    file_name = Sequence(lambda n: f"SmithvJones-app-Smith{n}-brf.pdf")
    content_type = "application/pdf"
    available = False
    doc_role = FilingRole.APPELLANT
    doc_party = "Smith"
    doc_type = FilingDocType.BRIEF
    local_path = Sequence(
        lambda n: f"{PRIVATE_PREFIX}nycourts_gov/"
        f"APL-2024-00177_smithvjones-app-smith{n}-brf_1.pdf"
    )


class NYCoAIssueFactory(Factory):
    """An issue as the scraper hands it over, already classified.

    The category and subcategory are classified off `category_raw` by the
    scraper's own classifier, so a test can state one string the way the Court
    does.
    """

    class Meta:
        model = NYCoAIssue

    category_raw = Faker("random_element", elements=_ISSUES)
    category = LazyAttribute(lambda o: classify_issue(o.category_raw).category)
    subcategory = LazyAttribute(
        lambda o: classify_issue(o.category_raw).subcategory
    )
    detail = Faker("text", max_nb_chars=60)


class NYCoAFilingFactory(Factory):
    """A filing as the scraper hands it over, already classified.

    The filing type, role and document type are drawn together, so they agree
    the way the FILINGS table makes them agree; see `_Filing`. Pass `filing=`
    to state one kind rather than take a random one. The classified filing type
    is read off `raw_filing_type` by the scraper's own classifier, so it is
    `None` when no table row named the filing and `None` when the table named a
    type the vocabulary does not cover.
    """

    class Meta:
        model = NYCoDocketEntry

    class Params:
        filing = Faker("random_element", elements=_FILINGS)

    # `e:<filing type>:<party>:<ordinal>`, the shape the scraper keys a filing
    # read from the FILINGS table with.
    docket_entry_id = LazyAttributeSequence(
        lambda o, n: f"e:{o.raw_filing_type.lower().replace(' ', '-')}:"
        f"{o.party.replace(' ', '')}:{n + 1}"
    )
    entry_index = Sequence(lambda n: n)
    entry_type = LazyAttribute(lambda o: o.filing.entry_type)
    raw_filing_type = LazyAttribute(lambda o: o.filing.filing_type.value)
    entry_filing_type = LazyAttribute(
        lambda o: filing_type_from_value(o.raw_filing_type)
    )
    party = Faker("name")
    date_filed = Faker("date_object")
    date_due = Faker("date_object")
    entry_role = LazyAttribute(lambda o: o.filing.role)
    entry_doctype = LazyAttribute(lambda o: o.filing.doctype)
    attachments = List([SubFactory(NYCoAFileFactory)])


class NYCoAAttorneyFactory(Factory):
    class Meta:
        model = NYCoAAttorney

    name = Faker("name")
    firm = Faker("company")
    address = Faker("address")
    # `Attorney.phone` is capped at 20 characters, which the `phone_number`
    # provider overruns; `basic_phone_number` stops at 13.
    phone = Faker("basic_phone_number")


class NYCoAPartyFactory(Factory):
    """A party on a Court-PASS docket, with the attorney representing it.

    The role the Court states and the standard type it maps to are drawn
    together; pass `role=` to state one rather than take a random one.
    """

    class Meta:
        model = NYCoAParty

    class Params:
        role = Faker("random_element", elements=_PARTY_ROLES)

    name = Faker("name")
    party_type = LazyAttribute(lambda o: o.role.party_type)
    party_role_raw = LazyAttribute(lambda o: o.role.raw)
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
    argument_date = Faker("date_object")
    decision_date = None
    issues = List([SubFactory(NYCoAIssueFactory)])
    official_citation = ""
    lower_court_citation = "102 AD3d 543"
    # Court-PASS publishes no transfer data, so a case never carries any.
    transfers = LazyFunction(list)
    entries = List([SubFactory(NYCoAFilingFactory)])
    parties = List([SubFactory(NYCoAPartyFactory)])
    # Court-PASS publishes no filing date for the case itself, so the scraper
    # reports the earliest date any of its filings was received.
    date_filed = LazyAttribute(
        lambda o: min(
            (entry.date_filed for entry in o.entries if entry.date_filed),
            default=None,
        )
    )
