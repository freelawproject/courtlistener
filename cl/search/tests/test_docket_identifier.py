from django.db import IntegrityError, transaction

from cl.search.factories import DocketFactory
from cl.search.models import DocketIdentifier
from cl.tests.cases import TestCase


class DocketIdentifierTest(TestCase):
    def test_create_and_str(self) -> None:
        docket = DocketFactory()
        identifier = DocketIdentifier.objects.create(
            docket=docket,
            type=DocketIdentifier.PATENT,
            value="7654321",
        )
        self.assertEqual(list(docket.identifiers.all()), [identifier])
        self.assertIn("7654321", str(identifier))

    def test_unique_per_docket_type_value(self) -> None:
        docket = DocketFactory()
        DocketIdentifier.objects.create(
            docket=docket, type=DocketIdentifier.PATENT, value="7654321"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocketIdentifier.objects.create(
                docket=docket, type=DocketIdentifier.PATENT, value="7654321"
            )
