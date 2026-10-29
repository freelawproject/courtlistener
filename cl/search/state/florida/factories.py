"""Factories used for testing functionality related to Florida state data."""

from datetime import UTC

from factory import Faker, SubFactory, post_generation
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.people_db.factories import PartyFactory
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
    status = FuzzyChoice(
        FloridaDocketEntry.STATUS_CHOICES, getter=lambda c: c[0]
    )
    docket_entry_uuid = Faker("uuid4")

    @post_generation
    def submitted_by(obj, create, extracted, **kwargs):
        """Attach a submitting party tied to the entry's docket, since
        PartyFactory's default attorney requires a docket."""
        if not create:
            return
        obj.submitted_by = extracted or PartyFactory(docket=obj.docket)
        obj.save()

    class Meta:
        model = FloridaDocketEntry


class FloridaDocumentFactory(DjangoModelFactory):
    docket_entry = SubFactory(FloridaDocketEntryFactory)
    content_type = "application/pdf"
    document_name = Faker("text", max_nb_chars=25)
    document_type = Faker("word")
    link_uuid = Faker("uuid4")
    page_count = Faker("pyint")
    url = Faker("url")

    class Meta:
        model = FloridaDocument
