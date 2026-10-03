from selenium.webdriver.support.ui import WebDriverWait
from waffle.testutils import override_flag

from cl.search.cluster_sources import ClusterSources
from cl.search.factories import (
    CourtFactory,
    DocketEntryFactory,
    DocketFactory,
    OpinionClusterWithChildrenAndParentsFactory,
    RECAPDocumentFactory,
)
from cl.search.models import Docket
from cl.tests.base import BaseSeleniumTest


@override_flag("use_new_design", active=False)
class DarkModeTest(BaseSeleniumTest):
    def create_recap_document(self):
        bankruptcy_court = CourtFactory(id="canb")
        recap_docket = DocketFactory(
            court=bankruptcy_court,
            source=Docket.RECAP,
            case_name="Bed Bath & Beyond Inc.",
        )
        docket_entry = DocketEntryFactory(docket=recap_docket)
        return RECAPDocumentFactory(
            docket_entry=docket_entry,
            filepath_local="test.pdf",
            is_available=True,
            plain_text="This is readable transcribed RECAP document text.",
        )

    def create_circuit_opinion(self):
        circuit_court = CourtFactory(id="ca9")
        opinion_cluster = OpinionClusterWithChildrenAndParentsFactory(
            docket=DocketFactory(court=circuit_court),
            source=ClusterSources.COURT_WEBSITE,
            case_name="Example v. Example",
        )
        opinion = opinion_cluster.sub_opinions.get()
        opinion.html = ""
        opinion.html_with_citations = (
            "This is readable text transcribed from a circuit court PDF."
        )
        opinion.save(update_fields=["html", "html_with_citations"])
        return opinion_cluster

    def enable_dark_mode(self) -> None:
        self.browser.get(self.live_server_url)
        self.browser.execute_script(
            "window.localStorage.setItem('cl-color-mode', 'dark');"
        )

    def assert_dark_document_text(self, selector: str) -> None:
        element = self.browser.find_element("css selector", selector)
        self.assertEqual(
            element.value_of_css_property("color"), "rgba(248, 250, 252, 1)"
        )
        self.assertEqual(
            self.browser.find_element(
                "tag name", "body"
            ).value_of_css_property("background-color"),
            "rgba(15, 23, 42, 1)",
        )

    def test_theme_toggle_applies_and_persists_dark_mode(self) -> None:
        self.browser.get(self.live_server_url)
        self.browser.execute_script(
            "window.localStorage.setItem('cl-color-mode', 'light');"
        )
        self.browser.refresh()

        toggle = self.browser.find_element("id", "dark-mode-toggle")
        root = self.browser.find_element("tag name", "html")
        body = self.browser.find_element("tag name", "body")
        light_background = body.value_of_css_property("background-color")

        self.assertEqual(root.get_attribute("data-color-mode"), "light")
        self.assertEqual(toggle.get_attribute("aria-pressed"), "false")
        self.assertEqual(toggle.get_attribute("aria-label"), "Use dark mode")

        toggle.click()

        self.assertEqual(root.get_attribute("data-color-mode"), "dark")
        self.assertEqual(toggle.get_attribute("aria-pressed"), "true")
        self.assertEqual(toggle.get_attribute("aria-label"), "Use light mode")
        self.assertEqual(
            self.browser.execute_script(
                "return window.localStorage.getItem('cl-color-mode');"
            ),
            "dark",
        )
        self.assertEqual(
            body.value_of_css_property("background-color"),
            "rgba(15, 23, 42, 1)",
        )
        self.assertNotEqual(
            body.value_of_css_property("background-color"), light_background
        )
        for mobile_toggle in self.browser.find_elements(
            "css selector", ".dark-mode-toggle--mobile"
        ):
            self.assertEqual(
                mobile_toggle.get_attribute("aria-pressed"), "true"
            )
            self.assertEqual(
                mobile_toggle.get_attribute("textContent").strip(),
                "Light Mode",
            )

        self.browser.refresh()

        root = self.browser.find_element("tag name", "html")
        toggle = self.browser.find_element("id", "dark-mode-toggle")
        self.assertEqual(root.get_attribute("data-color-mode"), "dark")
        self.assertEqual(toggle.get_attribute("aria-pressed"), "true")

    def test_recap_transcript_text_is_readable_in_dark_mode(self) -> None:
        recap_document = self.create_recap_document()
        self.enable_dark_mode()
        self.browser.get(
            f"{self.live_server_url}{recap_document.get_absolute_url()}"
        )

        self.assert_dark_document_text("#opinion-content pre")

    def test_mobile_theme_toggle_applies_dark_mode(self) -> None:
        self.browser.set_window_size(375, 812)
        try:
            self.browser.get(self.live_server_url)
            self.browser.execute_script(
                "window.localStorage.setItem('cl-color-mode', 'light');"
            )
            self.browser.refresh()
            self.browser.find_element("css selector", ".navbar-toggle").click()

            mobile_toggle = WebDriverWait(self.browser, 5).until(
                lambda driver: next(
                    (
                        toggle
                        for toggle in driver.find_elements(
                            "css selector", ".dark-mode-toggle--mobile"
                        )
                        if toggle.is_displayed()
                    ),
                    False,
                )
            )
            self.assertEqual(
                mobile_toggle.get_attribute("textContent").strip(), "Dark Mode"
            )

            mobile_toggle.click()

            self.assertEqual(
                self.browser.find_element("tag name", "html").get_attribute(
                    "data-color-mode"
                ),
                "dark",
            )
            self.assertEqual(
                mobile_toggle.get_attribute("aria-pressed"), "true"
            )
            self.assertEqual(
                mobile_toggle.get_attribute("textContent").strip(),
                "Light Mode",
            )
        finally:
            self.browser.set_window_size(1024, 768)

    def test_circuit_opinion_pdf_text_is_readable_in_dark_mode(self) -> None:
        opinion_cluster = self.create_circuit_opinion()
        self.enable_dark_mode()
        self.browser.get(
            f"{self.live_server_url}{opinion_cluster.get_absolute_url()}"
        )

        self.assert_dark_document_text(".subopinion-content .plaintext")
