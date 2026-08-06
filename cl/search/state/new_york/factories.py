"""Factories used for testing functionality related to New York Court of
Appeals state data."""

from factory import Faker, Sequence, SubFactory
from factory.django import DjangoModelFactory

from cl.search.factories import DocketFactory
from cl.search.state.new_york.models import (
    NYCoADocketEntry,
    NYCoADocketIssue,
    NYCoADocketMetadata,
    NYCoADocument,
)
from cl.search.state.new_york.vocabularies import (
    FilingDocType,
    FilingRole,
    FilingType,
    IssueCategory,
    IssueSubcategory,
)


class NYCoADocketMetadataFactory(DjangoModelFactory):
    docket = SubFactory(DocketFactory)
    decision_date = Faker("date")
    official_citation = Faker("text", max_nb_chars=25)
    lower_court_citation = Faker("text", max_nb_chars=25)

    class Meta:
        model = NYCoADocketMetadata


class NYCoADocketIssueFactory(DjangoModelFactory):
    metadata = SubFactory(NYCoADocketMetadataFactory)
    category = IssueCategory.JUDGMENTS
    subcategory = IssueSubcategory.CONFESSION_OF_JUDGMENT
    category_raw = Sequence(lambda n: f"Judgments--Confession of Judgment {n}")
    detail = Faker("text", max_nb_chars=60)

    class Meta:
        model = NYCoADocketIssue


class NYCoADocketEntryFactory(DjangoModelFactory):
    docket = SubFactory(DocketFactory)
    docket_entry_id = Sequence(lambda n: f"e:appellant-brief:smith:{n + 1}")
    entry_index = Sequence(lambda n: n)
    filing_type = FilingType.APPELLANT_BRIEF
    filing_type_raw = "Appellant Brief"
    filing_role = FilingRole.APPELLANT
    filing_doctype = FilingDocType.BRIEF
    filing_type_recognized = True
    party_name = Faker("name")
    date_filed = Faker("date")

    class Meta:
        model = NYCoADocketEntry


class NYCoADocumentFactory(DjangoModelFactory):
    docket_entry = SubFactory(NYCoADocketEntryFactory)
    file_name = Sequence(lambda n: f"SmithvJones-app-Smith-brf-{n + 1}.pdf")
    content_type = "application/pdf"
    available = Faker("boolean", chance_of_getting_true=75)
    doc_role = Faker("word")
    doc_party = Faker("name")
    doc_type = Faker("word")

    class Meta:
        model = NYCoADocument
