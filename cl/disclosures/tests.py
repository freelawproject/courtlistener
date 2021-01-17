import json
import os

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from cl.disclosures.models import (
    FinancialDisclosure,
    Investment,
    NonInvestmentIncome,
    Reimbursement,
)
from cl.disclosures.tasks import save_disclosure


class DisclosureIngestionTest(TestCase):
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


class LoggedInDisclosureTestCase(TestCase):
    fixtures = [
        "authtest_data.json",
        "disclosure.json",
        "judge_judy.json",
    ]

    def setUp(self):
        u = User.objects.get(pk=1001)
        ps = Permission.objects.filter(codename="has_disclosure_api_access")
        u.user_permissions.add(*ps)
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        self.q = dict()


class DisclosureAPIAccessTest(LoggedInDisclosureTestCase):
    def test_basic_disclosure_api_query(self):
        """Can we query the financial disclosures?"""
        url = reverse("financialdisclosure-list", kwargs={"version": "v3"})
        # 4 of the queries are from the setup
        with self.assertNumQueries(13):
            r = self.client.get(url)
        self.assertEqual(r.status_code, 200, msg="API failed.")
        self.assertEqual(r.json()["count"], 2, msg="Wrong API count.")

    def test_gift_disclosure_api(self):
        """Can we query the gifts?"""
        url = reverse("gift-list", kwargs={"version": "v3"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, msg="API failed.")
        self.assertEqual(r.json()["count"], 1, msg="Wrong API count")

    def test_investments_api(self):
        """Can we query the investments?"""
        url = reverse("investment-list", kwargs={"version": "v3"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, msg="API failed.")
        self.assertEqual(r.json()["count"], 9, msg="Wrong API count")

    def test_unauthorized_user(self):
        """Can a regular user access forbidden content?"""
        self.client.logout()
        url = reverse("gift-list", kwargs={"version": "v3"})
        r = self.client.get(url)
        self.assertEqual(
            r.status_code, 401, msg="Unauthorized content exposed."
        )

    def test_access_to_content_outside_authorization(self):
        """Can a admin user access forbidden content?"""
        self.client.login(username="admin", password="admin")
        url = reverse("gift-list", kwargs={"version": "v3"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, msg="Admin lacking access.")


class DisclosureAPITest(LoggedInDisclosureTestCase):
    def test_basic_disclosure_api_query(self):
        """Can we query the financial disclosure API?"""
        self.path = reverse("financialdisclosure-list", kwargs={"version": "v3"})
        r = self.client.get(self.path)
        self.assertEqual(r.status_code, 200, msg="API failed.")
        self.assertEqual(r.json()["count"], 2, msg="Wrong API count")

    def test_disclosure_position_api(self):
        """Can we query the financial disclosure API?"""
        self.path = reverse(
            "disclosureposition-list", kwargs={"version": "v3"}
        )
        r = self.client.get(self.path)
        self.assertEqual(r.status_code, 200, msg="API failed.")
        self.assertEqual(r.json()["count"], 2, msg="Wrong API count")

    def test_investment_filtering(self):
        """Can we filter investments by transaction value codes?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"transaction_value_code": "M"}
        r = self.client.get(self.path, self.q)
        self.assertEqual(r.json()["count"], 1, msg="Wrong Investment filter")

    def test_exact_filtering_by_id(self):
        """Can we filter investments by id?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"id": 878}
        r = self.client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"], 1, msg="Investment filtering by id failed."
        )

    def test_filtering_description_by_text(self):
        """Can we filter by description partial text?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"description__startswith": "Harris Bank"}
        r = self.client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"], 2, msg="Investment filtering by id failed."
        )

    def test_filter_investments_by_redaction(self):
        """Can we filter investments by redaction boolean?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"redacted": True}
        r = self.client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"],
            3,
            msg="Investment filtering by redactions failed.",
        )

    def test_filter_disclosures_by_person_id(self):
        """Can we filter disclosures by person id?"""
        self.path = reverse(
            "financialdisclosure-list", kwargs={"version": "v3"}
        )
        self.q = {"person": 2}
        r = self.client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"],
            1,
            msg="Incorrect disclosures found.",
        )
