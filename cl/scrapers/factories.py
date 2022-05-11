from factory import Faker, Iterator
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.scrapers.models import PACERFreeDocumentLog
from cl.search.models import Court


class PACERFreeDocumentLogFactory(DjangoModelFactory):
    class Meta:
        model = PACERFreeDocumentLog

    court = Iterator(Court.objects.all())
    date_queried = Faker("date_object")
    status = FuzzyChoice(
        PACERFreeDocumentLog.SCRAPE_STATUSES, getter=lambda c: c[0]
    )
