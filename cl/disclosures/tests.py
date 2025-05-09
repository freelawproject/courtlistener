import json
import os

from asgiref.sync import sync_to_async
from django.conf import settings
from django.urls import reverse
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from timeout_decorator import timeout_decorator

from cl.disclosures.factories import (
    DebtFactory,
    FinancialDisclosureFactory,
    FinancialDisclosurePositionFactory,
    GiftFactory,
    InvestmentFactory,
    ReimbursementFactory,
    SpousalIncomeFactory,
)
from cl.disclosures.models import (
    CODES,
    FinancialDisclosure,
    Investment,
    NonInvestmentIncome,
    Reimbursement,
)
from cl.disclosures.tasks import save_disclosure
from cl.lib.microservice_utils import microservice
from cl.people_db.factories import PersonWithChildrenFactory
from cl.people_db.models import Person
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import TestCase


class DisclosureIngestionTest(TestCase):
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

    @classmethod
    def setUpTestData(cls) -> None:
        judge = PersonWithChildrenFactory.create()
        cls.test_disclosure = FinancialDisclosureFactory.create(
            person=judge,
        )
        FinancialDisclosureFactory.create(
            person=judge,
        )

    def test_financial_disclosure_ingestion(self) -> None:
        """Can we successfully ingest disclosures at a high level?"""

        with open(self.test_file) as f:
            extracted_data = json.load(f)
        Investment.objects.all().delete()

        save_disclosure(
            extracted_data=extracted_data,
            disclosure=self.test_disclosure,
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

    async def test_extraction_and_ingestion_jef(self) -> None:
        """Can we successfully ingest disclosures from jef documents?"""
        with open(self.jef_pdf, "rb") as f:
            pdf_bytes = f.read()
        await Investment.objects.all().adelete()

        extracted_data = await microservice(
            service="extract-disclosure",
            file_type="pdf",
            file=pdf_bytes,
        )

        await sync_to_async(save_disclosure)(
            extracted_data=extracted_data.json(),
            disclosure=self.test_disclosure,
        )
        investments = Investment.objects.all()
        investment_count = await investments.acount()
        self.assertEqual(
            investment_count,
            84,
            "Should have 84 ingested investments",
        )


class DisclosureAPITest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.judge = PersonWithChildrenFactory.create()
        fd = FinancialDisclosureFactory.create(
            person=cls.judge,
        )
        FinancialDisclosurePositionFactory.create_batch(
            2, financial_disclosure=fd
        )
        InvestmentFactory.create(
            financial_disclosure=fd,
            transaction_value_code=CODES.A,
            description="Harris Bank Inc",
        )
        cls.investment_for_id = InvestmentFactory.create(
            financial_disclosure=fd,
            transaction_value_code=CODES.M,
            description="Harris Bank and Trust Company",
        )
        InvestmentFactory.create(
            financial_disclosure=fd,
            transaction_value_code=CODES.B,
        )
        InvestmentFactory.create_batch(
            10, financial_disclosure=fd, redacted=True
        )
        DebtFactory.create(
            financial_disclosure=fd, creditor_name="JP Morgan Chase"
        )
        DebtFactory.create_batch(10, financial_disclosure=fd, redacted=False)
        SpousalIncomeFactory.create(
            financial_disclosure=fd,
            source_type="A big Trust Fund",
        )
        SpousalIncomeFactory.create_batch(
            10, financial_disclosure=fd, redacted=False
        )
        GiftFactory.create(
            financial_disclosure=fd,
            source="John Oliver",
            description="Luxury Motor Coach",
            value="2,000,000.00 dollars",
        )
        GiftFactory.create_batch(10, financial_disclosure=fd, redacted=False)
        ReimbursementFactory.create(
            financial_disclosure=fd,
            location="Honolulu, Hawaii",
        )
        ReimbursementFactory.create_batch(
            10, financial_disclosure=fd, redacted=False
        )

    async def test_disclosure_position_api(self) -> None:
        """Can we query the financial disclosure position API?"""
        self.path = reverse(
            "disclosureposition-list", kwargs={"version": "v3"}
        )
        r = await self.async_client.get(self.path)
        self.assertEqual(r.status_code, 200, msg="API failed.")
        self.assertEqual(r.json()["count"], 2, msg="Wrong API count")
        self.assertIn(
            "disclosure-positions",
            r.json()["results"][0]["resource_uri"],
            msg="Incorrect resource URI",
        )

    async def test_investment_filtering(self) -> None:
        """Can we filter investments by transaction value codes?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"transaction_value_code": CODES.M}
        r = await self.async_client.get(self.path, self.q)
        self.assertEqual(r.json()["count"], 1, msg="Wrong Investment filter")

    async def test_exact_filtering_by_id(self) -> None:
        """Can we filter investments by id?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"id": self.investment_for_id.id}
        r = await self.async_client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"], 1, msg="Investment filtering by id failed."
        )

    async def test_filtering_description_by_text(self) -> None:
        """Can we filter by description partial text?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"description__startswith": "Harris Bank"}
        r = await self.async_client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"], 2, msg="Investment filtering by id failed."
        )

    async def test_filter_investments_by_redaction(self) -> None:
        """Can we filter investments by redaction boolean?"""
        self.path = reverse("investment-list", kwargs={"version": "v3"})
        self.q = {"redacted": True}
        r = await self.async_client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"],
            10,
            msg="Investment filtering by redactions failed.",
        )

    async def test_filter_disclosures_by_person_id(self) -> None:
        """Can we filter disclosures by person id?"""
        self.path = reverse(
            "financialdisclosure-list", kwargs={"version": "v3"}
        )
        self.q = {"person": self.judge.id}
        r = await self.async_client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"],
            1,
            msg="Incorrect disclosures found.",
        )

    async def test_filter_related_object(self) -> None:
        """Can we filter disclosures by transaction value code?"""
        self.path = reverse(
            "financialdisclosure-list", kwargs={"version": "v3"}
        )
        q = {"investments__transaction_value_code": CODES.M}

        r = await self.async_client.get(self.path, q)
        self.assertEqual(r.json()["count"], 1, msg="Wrong disclosure count")

    async def test_gift_filtering(self) -> None:
        """Can we filter gifts by description?"""
        self.path = reverse("gift-list", kwargs={"version": "v3"})
        self.q = {"description": "Luxury Motor Coach"}
        r = await self.async_client.get(self.path, self.q)
        self.assertEqual(r.json()["count"], 1, msg="Failed Gift filter")

    async def test_reimbursement_filtering(self) -> None:
        """Can we filter reimbursements by location?"""
        self.path = reverse("reimbursement-list", kwargs={"version": "v3"})
        self.q = {"location__icontains": "hawaii"}
        r = await self.async_client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"], 1, msg="Failed Reimbursement filter"
        )

    async def test_spousal_income_filtering(self) -> None:
        """Can we filter spousal income by source_type?"""
        self.path = reverse("spouseincome-list", kwargs={"version": "v3"})
        self.q = {"source_type__icontains": "trust fund"}
        r = await self.async_client.get(self.path, self.q)
        self.assertEqual(
            r.json()["count"], 1, msg="Failed Spousal Income filter"
        )

    async def test_debt_filtering(self) -> None:
        """Can we filter debts by creditor?"""
        self.path = reverse("debt-list", kwargs={"version": "v3"})
        self.q = {"creditor_name__icontains": "JP Morgan"}
        r = await self.async_client.get(self.path, self.q)
        self.assertEqual(r.json()["count"], 1, msg="Failed Debt filter")


class DisclosureReactLoadTest(BaseSeleniumTest):
    def setUp(self) -> None:
        judge = PersonWithChildrenFactory.create(
            name_first="Judith",
            name_middle="",
            name_last="Baker",
        )
        FinancialDisclosureFactory.create(
            person=judge,
        )

    def tearDown(self) -> None:
        FinancialDisclosure.objects.all().delete()
        Person.objects.all().delete()
        super().tearDown()

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_disclosure_homepage(self) -> None:
        """Can we load disclosure homepage?"""
        wait = WebDriverWait(self.browser, 3)
        self.browser.get(self.live_server_url)
        dropdown = self.browser.find_element(By.ID, "navbar-fd")
        dropdown.click()
        link = self.browser.find_element(
            By.LINK_TEXT, "Search Financial Disclosures"
        )
        link.click()
        self.assertIn(
            "Judicial Financial Disclosures Database", self.browser.title
        )
        search_bar = wait.until(
            EC.visibility_of_element_located((By.ID, "main-query-box"))
        )
        self.assertTrue(
            search_bar.is_displayed(), msg="React-root failed to load"
        )

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_disclosure_search(self) -> None:
        """Can we search for judges?"""
        wait = WebDriverWait(self.browser, 3)
        self.browser.get(self.live_server_url)
        self.browser.implicitly_wait(2)
        self.browser.find_element(By.ID, "navbar-fd").click()
        self.browser.find_element(
            By.LINK_TEXT, "Search Financial Disclosures"
        ).click()
        self.assertIn(
            "Judicial Financial Disclosures Database", self.browser.title
        )
        search_bar = wait.until(
            EC.visibility_of_element_located((By.ID, "main-query-box"))
        )
        self.assertTrue(
            search_bar.is_displayed(), msg="React-root failed to load"
        )

        with self.assertRaises(NoSuchElementException):
            self.browser.find_element(By.CSS_SELECTOR, ".tr-results")

        search_bar = self.browser.find_element(By.ID, "id_disclosures_search")
        search_bar.send_keys("Judith")
        results = self.browser.find_elements(By.CSS_SELECTOR, ".tr-results")
        self.assertEqual(len(results), 1, msg="Incorrect results displayed")
