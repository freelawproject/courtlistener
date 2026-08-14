"""Factories used for testing functionality related to New York Court of
Appeals state data."""

import random
from datetime import timedelta

from factory import Faker, Sequence, SubFactory, post_generation
from factory.declarations import LazyAttribute
from factory.django import DjangoModelFactory

from cl.people_db.factories import PartyFactory
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
    category = IssueCategory.JUDGMENTS.code
    subcategory = IssueSubcategory.CONFESSION_OF_JUDGMENT.code
    category_raw = Sequence(lambda n: f"Judgments--Confession of Judgment {n}")
    detail = Faker("text", max_nb_chars=60)

    class Meta:
        model = NYCoADocketIssue


class NYCoADocketEntryFactory(DjangoModelFactory):
    docket = SubFactory(DocketFactory)
    docket_entry_id = Sequence(lambda n: f"e:appellant-brief:smith:{n + 1}")
    entry_index = Sequence(lambda n: n)
    filing_type = FilingType.APPELLANT_BRIEF
    filing_type_raw = FilingType.APPELLANT_BRIEF.label
    filing_role = FilingRole.APPELLANT
    filing_doctype = FilingDocType.BRIEF
    filing_type_recognized = True
    party_name = Faker("name")
    date_filed = Faker("date_object")
    date_due = LazyAttribute(
        lambda d: d.date_filed + timedelta(days=random.randint(7, 60))
        if d.date_filed
        else None
    )

    @post_generation
    def party(obj, create, extracted, **kwargs):
        """Attach a filing party tied to the entry's docket, since
        PartyFactory's default attorney requires a docket."""
        if not create:
            return
        obj.party = extracted or PartyFactory(docket=obj.docket)
        obj.save()

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
    page_count = Faker("pyint")
    # Court-PASS serves every document from one POST endpoint
    url = "https://courtpass.nycourts.gov/Docket"
    volume = LazyAttribute(
        lambda d: random.randint(1, 5) if random.random() < 0.2 else None
    )
    part = LazyAttribute(
        lambda d: random.randint(1, 3)
        if d.volume and random.random() < 0.5
        else None
    )

    class Meta:
        model = NYCoADocument
