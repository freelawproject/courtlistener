from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from cl.citations.models import UnmatchedCitationFromRECAPDocument
from cl.search.factories import RECAPDocumentFactory
from cl.search.models import Citation


class UnmatchedCitationFromRECAPDocumentFactory(DjangoModelFactory):
    """Make an UnmatchedCitationFromRECAPDocument with a citing document."""

    class Meta:
        model = UnmatchedCitationFromRECAPDocument

    citing_recapdocument = SubFactory(RECAPDocumentFactory)
    status = UnmatchedCitationFromRECAPDocument.NO_CITATION
    citation_string = Faker("text", max_nb_chars=20)
    court_id = ""
    volume = Faker("numerify", text="##")
    reporter = "U.S."
    page = Faker("numerify", text="###")
    type = Citation.FEDERAL
