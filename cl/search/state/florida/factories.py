"""Factories used for testing functionality related to Florida state data."""

from datetime import UTC

from factory import Faker, SubFactory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.people_db.factories import PersonFactory
from cl.search.factories import DocketFactory
from cl.search.state.florida.models import FloridaDocketEntry, FloridaDocument
from cl.search.state.shared import DocketEntryType


class FloridaDocketEntryFactory(DjangoModelFactory):
    docket = SubFactory(DocketFactory)
    date_filed = Faker("date_time", tzinfo=UTC)
    date_submitted = Faker("date_time", tzinfo=UTC)
    entry_type = FuzzyChoice(DocketEntryType.CHOICES, getter=lambda c: c[0])
    entry_type_raw = Faker("word")
    entry_name = Faker("text", max_nb_chars=25)
    description = Faker("text", max_nb_chars=25)
    submitted_by = SubFactory(PersonFactory)
    status = Faker("word")
    docket_entry_uuid = Faker("uuid4")

    class Meta:
        model = FloridaDocketEntry


class FloridaDocumentFactory(DjangoModelFactory):
    docket_entry = SubFactory(FloridaDocketEntryFactory)
    content_type = "application/pdf"
    document_name = Faker("text", max_nb_chars=25)
    document_type = Faker("word")
    description = Faker("text", max_nb_chars=25)
    link_uuid = Faker("uuid4")
    url = Faker("url")

    class Meta:
        model = FloridaDocument
