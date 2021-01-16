import json
import os

from django.conf import settings
from django.test import TestCase

from cl.disclosures.models import (
    FinancialDisclosure,
    Investment,
    NonInvestmentIncome,
    Reimbursement,
)
from cl.disclosures.tasks import save_disclosure


class DisclosureIngestionTests(TestCase):
    fixtures = ["judge_judy.json", "disclosure.json"]
    test_file = os.path.join(
        settings.INSTALL_ROOT,
        "cl",
        "disclosures",
        "test_assets",
        "disclosure_test_asset.json",
    )

    def test_financial_disclosure_ingestion(self):
        """Can we successfully ingest disclosures at a high level?"""

        test_disclosure = FinancialDisclosure.objects.get(pk=1)
        with open(self.test_file, "r") as f:
            extracted_data = json.load(f)

        save_disclosure(
            extracted_data=extracted_data,
            disclosure=test_disclosure,
        )
        investments = Investment.objects.all()
        reimbursements = Reimbursement.objects.all()
        non_investments = NonInvestmentIncome.objects.all()
        self.assertTrue(
            investments.count() == 19,
            "Should have 19 ingested investments, not %s"
            % investments.count(),
        )
        self.assertTrue(
            reimbursements.count() == 5,
            "Should have 5 ingested reimbursements, not %s"
            % reimbursements.count(),
        )
        self.assertTrue(
            non_investments.count() == 2,
            "Should have 2 ingested non-investments, not %s"
            % non_investments.count(),
        )
