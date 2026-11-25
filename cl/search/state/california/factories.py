"""Factories used for testing functionality related to California state data."""

from datetime import UTC
from typing import Any

from factory import Faker, Sequence, SubFactory, post_generation
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice
from factory.random import randgen

from cl.people_db.factories import PartyFactory
from cl.people_db.models import Party
from cl.search.factories import DocketFactory
from cl.search.state.california.models import (
    CADocumentType,
    CaliforniaDocketEntry,
    CaliforniaDocument,
)


class CaliforniaDocketEntryFactory(DjangoModelFactory):
    """Make a California docket entry on a new docket."""

    docket = SubFactory(DocketFactory)
    brief = Faker("pybool")
    description = Faker("text", max_nb_chars=25)
    notes = Faker("text", max_nb_chars=25)
    date_filed = Faker("date_time", tzinfo=UTC)
    submitted_by_name = Faker("name")

    @post_generation
    @staticmethod
    def submitted_by(
        obj: CaliforniaDocketEntry,
        create: bool,
        extracted: Party | None,
        **kwargs: Any,
    ) -> None:
        """Attach a submitting party tied to the entry's docket, since PartyFactory's default attorney requires a docket.

        Without an explicit party, about one in five entries is left
        unlinked, as happens when the submitting party can't be found.
        """
        if not create:
            return
        if not extracted and randgen.random() < 0.2:
            return
        obj.submitted_by = extracted or PartyFactory(docket=obj.docket)
        obj.save()

    class Meta:
        model = CaliforniaDocketEntry


class CaliforniaDocumentFactory(DjangoModelFactory):
    """Make a California PDF document on a new docket entry."""

    docket_entry = SubFactory(CaliforniaDocketEntryFactory)
    document_number = Sequence(lambda n: n + 1)
    description = Faker("text", max_nb_chars=25)
    document_type = FuzzyChoice(CADocumentType.values)
    document_type_raw = Faker("word")
    file_name = Sequence(lambda n: f"S{n + 100000}_brief.pdf")
    url = Faker("url")

    class Meta:
        model = CaliforniaDocument
