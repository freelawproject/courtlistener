import json
import os

import requests
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator

from cl.disclosures.models import (
    FinancialDisclosure,
    Investment,
    NonInvestmentIncome,
    Reimbursement,
)
from cl.disclosures.tasks import save_disclosure
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import TestCase


class DisclosureIngestionTest(TestCase):
    fixtures = ["judge_judy.json", "disclosure.json"]
    test_file = os.path.join(
        settings.INSTALL_ROOT,
        "cl",
        "disclosures",
        "test_assets",
        "disclosure_test_asset.json",
    )
    jef_pdf = os.path.join(
        settings.INSTALL_ROOT,
        "cl",
        "disclosures",
        "test_assets",
        "JEF_format.pdf",
    )

    def test_financial_disclosure_ingestion(self) -> None:
        """Can we successfully ingest disclosures at a high level?"""

        test_disclosure = FinancialDisclosure.objects.get(pk=1)
        with open(self.test_file, "r") as f:
            extracted_data = json.load(f)
        Investment.objects.all().delete()

        save_disclosure(
            extracted_data=extracted_data,
            disclosure=test_disclosure,
        )
        investments = Investment.objects.all()
        reimbursements = Reimbursement.objects.all()
        non_investments = NonInvestmentIncome.objects.all()
        self.assertTrue(
            investments.count() == 19,
            f"Should have 19 ingested investments, not {investments.count()}",
        )
        self.assertTrue(
            reimbursements.count() == 5,
            f"Should have 5 ingested reimbursements, not {reimbursements.count()}",
        )
        self.assertTrue(
            non_investments.count() == 2,
            f"Should have 2 ingested non-investments, not {non_investments.count()}",
        )

    def test_extraction_and_ingestion_jef(self) -> None:
        """Can we successfully ingest disclosures from jef documents?"""
        with open(self.jef_pdf, "rb") as f:
            pdf_bytes = f.read()
        Investment.objects.all().delete()
        extractor_response = requests.post(
            settings.BTE_URLS["extract-disclosure-jef"]["url"],
            files={"file": ("file", pdf_bytes)},
            timeout=settings.BTE_URLS["extract-disclosure-jef"]["timeout"],
        )
        extracted_data = extractor_response.json()
        test_disclosure = FinancialDisclosure.objects.get(pk=1)
        save_disclosure(
            extracted_data=extracted_data,
            disclosure=test_disclosure,
        )
        investments = Investment.objects.all()
        investment_count = investments.count()
        self.assertEqual(
            investment_count,
            84,
            f"Should have 84 ingested investments",
        )


class LoggedInDisclosureTestCase(TestCase):
    fixtures = [
        "authtest_data.json",
        "disclosure.json",
        "judge_judy.json",
    ]

    def setUp(self) -> None:
        u = User.objects.get(pk=1001)
        ps = Permission.objects.filter(codename="has_disclosure_api_access")
        u.user_permissions.add(*ps)
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        self.q = dict()


class DisclosureAPIAccessTest(LoggedInDisclosureTestCase):
    def test_basic_disclosure_api_query(self) -> None:
        """Can we query the financial disclosures?"""
        url = reverse("financialdisclosure-list", kwargs={"version": "v3"})
        # 4 of the queries are from the setup
        with self.assertNumQueries(12):
            r = self.client.get(url)
        self.assertEqual(r.status_code, 200, msg="API failed.")
        self.assertEqual(r.json()["count"], 2, msg="Wrong API count.")

    def test_gift_disclosure_api(self) -> None:
        """Can we query the gifts?"""
        url = reverse("gift-list", kwargs={"version": "v3"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, msg="API failed.")
        self.assertEqual(r.json()["count"], 1, msg="Wrong API count")

    def test_investments_api(self) -> None:
        """Can we query the investments?"""
        url = reverse("investment-list", kwargs={"version": "v3"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, msg="API failed.")
        self.assertEqual(r.json()["count"], 9, msg="Wrong API count")

    def test_anonymous_user(self) -> None:
        """Can an anonymous user access disclosure content?"""
        self.client.logout()
        url = reverse("gift-list", kwargs={"version": "v3"})
        r = self.client.get(url)
        self.assertEqual(
            r.status_code, 200, msg="Unauthorized content exposed."
        )

    def test_access_to_content_outside_authorization(self) -> None:
        """Can a admin user access forbidden content?"""
        self.client.login(username="admin", password="admin")
        url = reverse("gift-list", kwargs={"version": "v3"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, msg="Admin lacking access.")


class DisclosureAPITest(LoggedInDisclosureTestCase):
    def test_disclosure_position_api(self) -> None:
        """Can we query the financial disclosure position API?"""
        self.path = reverse(
            "disclosureposition-list", kwargs={"version": "v3"}
        )
        r = self.client.get(self.path)
        self.assertEqual(r.status_code, 200, msg="API failed.")
        self.assertEqual(r.json()["count"], 2, msg="Wrong API count")
        self.assertIn(
            "disclosure-positions",
            r.json()["results"][0]["resource_uri"],
            msg="Incorrect resource URI",
        )

    def test_investment_filtering(self) -> None:
        """Can we filter investments by transaction value codes?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"transaction_value_code": "M"}
        r = self.client.get(self.path, self.q)
        self.assertEqual(r.json()["count"], 1, msg="Wrong Investment filter")

    def test_exact_filtering_by_id(self) -> None:
        """Can we filter investments by id?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"id": 878}
        r = self.client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"], 1, msg="Investment filtering by id failed."
        )

    def test_filtering_description_by_text(self) -> None:
        """Can we filter by description partial text?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"description__startswith": "Harris Bank"}
        r = self.client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"], 2, msg="Investment filtering by id failed."
        )

    def test_filter_investments_by_redaction(self) -> None:
        """Can we filter investments by redaction boolean?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"redacted": True}
        r = self.client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"],
            3,
            msg="Investment filtering by redactions failed.",
        )

    def test_filter_disclosures_by_person_id(self) -> None:
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

    def test_filter_related_object(self) -> None:
        """Can we filter disclosures by transaction value code?"""
        self.path = reverse(
            "financialdisclosure-list", kwargs={"version": "v3"}
        )
        self.q["investments__transaction_value_code"] = "M"

        r = self.client.get(self.path, self.q)
        self.assertEqual(r.json()["count"], 1, msg="Wrong disclosure count")


class DisclosureReactLoadTest(BaseSeleniumTest):

    fixtures = [
        "test_court.json",
        "authtest_data.json",
        "disclosure.json",
        "judge_judy.json",
    ]

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_disclosure_homepage(self) -> None:
        """Can we load disclosure homepage?"""
        self.browser.get(self.live_server_url)
        link = self.browser.find_element(By.ID, "navbar-fd")
        link.click()
        self.assertIn(
            "Judicial Financial Disclosures Database", self.browser.title
        )
        search_bar = self.browser.find_element(By.ID, "main-query-box")
        self.assertTrue(
            search_bar.is_displayed(), msg="React-root failed to load"
        )
