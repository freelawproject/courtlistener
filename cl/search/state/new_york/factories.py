"""Factories used for testing functionality related to New York Court of
Appeals state data."""

from factory import Faker, Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.search.factories import DocketFactory
from cl.search.state.new_york.models import (
    NYCoADocketEntry,
    NYCoADocketMetadata,
    NYCoADocument,
)


class NYCoADocketMetadataFactory(DjangoModelFactory):
    docket = SubFactory(DocketFactory)
    issue = Faker("text", max_nb_chars=25)
    summary = Faker("text", max_nb_chars=25)
    decision_date = Faker("date")
    opinion_by = Faker("name")
    official_citation = Faker("text", max_nb_chars=25)

    class Meta:
        model = NYCoADocketMetadata


class NYCoADocketEntryFactory(DjangoModelFactory):
    docket = SubFactory(DocketFactory)
    page = FuzzyChoice(
        NYCoADocketEntry.EntryPage.choices, getter=lambda c: c[0]
    )
    filing_type = Faker("text", max_nb_chars=25)
    party = Faker("text", max_nb_chars=25)
    date_received = Faker("date")
    sequence_number = Sequence(lambda n: str(n).zfill(16))

    class Meta:
        model = NYCoADocketEntry


class NYCoADocumentFactory(DjangoModelFactory):
    docket_entry = SubFactory(NYCoADocketEntryFactory)
    file_name = Faker("file_name", extension="pdf")
    document_number = Sequence(lambda n: n + 1)
    available = True

    class Meta:
        model = NYCoADocument
