import logging
from bs4 import BeautifulSoup
import bs4
from cl.tests.cases import TestCase
from cl.search.management.commands.update_cap_cases import Command

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class UpdateCapCasesTest(TestCase):
    def setUp(self):
        super().setUp()
        self.command = Command()

    def test_update_cap_html_with_cl_xml_simple(self):
        # Simple case: Update various paragraph types
        cap_html = """
        <section class="casebody">
            <article class="opinion" data-type="majority">
                <p class="author" id="b1">AUTHOR NAME</p>
                <p id="b2">Some opinion text</p>
                <p class="summary" id="b3">Case summary</p>
                <p id="b4">More text</p>
            </article>
        </section>
        """

        cl_xml_list = [
            {
                "id": 1,
                "type": "majority",
                "xml": """
            <opinion type="majority">
                <author id="b1">AUTHOR NAME</author>
                <p id="b2">Some opinion text</p>
                <summary id="b3">Case summary</summary>
                <aside id="b4">More text</aside>
            </opinion>
            """,
            }
        ]

        processed_opinions, changes = self.command.update_cap_html_with_cl_xml(
            cap_html, cl_xml_list
        )

        self.assertEqual(len(processed_opinions), 1)

        # Parse the processed XML to check structure
        soup = BeautifulSoup(processed_opinions[0]["xml"], "xml")

        # Check the overall structure
        opinion_tag = soup.find("opinion")
        self.assertIsNotNone(opinion_tag)
        self.assertEqual(opinion_tag.get("type"), "majority")

        # Check that various tags are present
        author_tag = opinion_tag.find("author")
        self.assertIsNotNone(author_tag)
        self.assertEqual(author_tag.get("id"), "b1")
        self.assertEqual(author_tag.text.strip(), "AUTHOR NAME")

        p_tag = opinion_tag.find("p")
        self.assertIsNotNone(p_tag)
        self.assertEqual(p_tag.get("id"), "b2")
        self.assertEqual(p_tag.text.strip(), "Some opinion text")

        summary_tag = opinion_tag.find("summary")
        self.assertIsNotNone(summary_tag)
        self.assertEqual(summary_tag.get("id"), "b3")
        self.assertEqual(summary_tag.text.strip(), "Case summary")

        aside_tag = opinion_tag.find("aside")
        self.assertIsNotNone(aside_tag)
        self.assertEqual(aside_tag.get("id"), "b4")
        self.assertEqual(aside_tag.text.strip(), "More text")

        self.assertIsNone(soup.find("p", class_="author"))
        self.assertIsNone(soup.find("p", class_="summary"))

        # Check that there are only four direct children of the opinion tag
        self.assertEqual(len(opinion_tag.find_all(recursive=False)), 4)

        # Verify the order of elements
        children = list(opinion_tag.children)
        self.assertTrue(
            isinstance(children[0], bs4.element.Tag)
            and children[0].name == "author"
        )
        self.assertTrue(
            isinstance(children[1], bs4.element.Tag)
            and children[1].name == "p"
        )
        self.assertTrue(
            isinstance(children[2], bs4.element.Tag)
            and children[2].name == "summary"
        )
        self.assertTrue(
            isinstance(children[3], bs4.element.Tag)
            and children[3].name == "aside"
        )

        # Check that the changes list reflects the updates
        expected_changes = [
            "Updated element b1 type from p to author",
            "Updated element b3 type from p to summary",
            "Updated element b4 type from p to aside",
        ]
        self.assertEqual(set(changes), set(expected_changes))

    def test_update_cap_html_with_no_opinion_content(self):
        # Case: CL XML includes an opinion not present in CAP HTML
        cap_html = """
        <section class="casebody">
            <article class="opinion" data-type="majority">
                <p class="author" id="b1">AUTHOR NAME</p>
                <p id="b2">Some opinion text</p>
            </article>
        </section>
        """

        cl_xml_list = [
            {
                "id": 1,
                "type": "majority",
                "xml": """
        <opinion type="majority">
            <author id="b1">AUTHOR NAME</author>
            <p id="b2">Some opinion text</p>
        </opinion>
        """,
            },
            {
                "id": 2,
                "type": "concurrence",
                "xml": """
        <opinion type="concurrence">
            <author>CONCURRING JUDGE</author>
            <p>No opinion found.</p>
        </opinion>
        """,
            },
        ]

        processed_opinions, changes = self.command.update_cap_html_with_cl_xml(
            cap_html, cl_xml_list
        )

        self.assertEqual(len(processed_opinions), 2)

        # Check the majority opinion
        majority_soup = BeautifulSoup(processed_opinions[0]["xml"], "xml")
        majority_opinion = majority_soup.find("opinion")
        self.assertEqual(majority_opinion["type"], "majority")
        self.assertEqual(len(majority_opinion.find_all(recursive=False)), 2)

        # Check the concurrence opinion (should be unchanged from CL XML)
        concurrence_soup = BeautifulSoup(processed_opinions[1]["xml"], "xml")
        concurrence_opinion = concurrence_soup.find("opinion")
        self.assertEqual(concurrence_opinion["type"], "concurrence")
        self.assertEqual(len(concurrence_opinion.find_all(recursive=False)), 2)
        self.assertEqual(
            concurrence_opinion.author.text.strip(), "CONCURRING JUDGE"
        )
        self.assertEqual(
            concurrence_opinion.p.text.strip(), "No opinion found."
        )

        # Check that the changes list reflects the use of existing CL XML for concurrence
        self.assertIn(
            "Used existing CL XML for concurrence opinion (no match in CAP HTML)",
            changes,
        )

    def test_update_cap_html_with_extra_cap_opinion(self):
        # Case: CAP HTML includes an opinion not present in CL XML
        cap_html = """
        <section class="casebody">
            <article class="opinion" data-type="majority">
                <p class="author" id="b1">AUTHOR NAME</p>
                <p id="b2">Some opinion text</p>
            </article>
            <article class="opinion" data-type="dissent">
                <p class="author" id="b3">DISSENTING JUDGE</p>
                <p id="b4">Dissent text</p>
            </article>
        </section>
        """

        cl_xml_list = [
            {
                "id": 1,
                "type": "majority",
                "xml": """
        <opinion type="majority">
            <author id="b1">UPDATED AUTHOR NAME</author>
            <p id="b2">Updated opinion text</p>
        </opinion>
        """,
            }
        ]

        processed_opinions, changes = self.command.update_cap_html_with_cl_xml(
            cap_html, cl_xml_list
        )

        # Check the number of processed opinions
        self.assertEqual(
            len(processed_opinions),
            1,
            "Only the majority opinion should be processed",
        )

        # Check that only the majority opinion is in the processed opinions
        self.assertEqual(
            processed_opinions[0]["type"],
            "majority",
            "Only the majority opinion should be in the processed opinions",
        )

        # Check the content of the majority opinion
        majority_soup = BeautifulSoup(processed_opinions[0]["xml"], "xml")
        self.assertEqual(
            majority_soup.author.text,
            "AUTHOR NAME",
            "The author name should be preserved from CAP HTML",
        )
        self.assertEqual(
            majority_soup.p.text,
            "Some opinion text",
            "The opinion text should be preserved from CAP HTML",
        )

        # Check that there's no note about the dissent opinion
        self.assertNotIn("Preserved dissent opinion from CAP HTML", changes)
        self.assertNotIn("Updated content for majority opinion", changes)

    def test_update_cap_html_with_extra_cap_content(self):
        # Case: CAP HTML includes extra content within a matching opinion
        cap_html = """
        <section class="casebody">
            <article class="opinion" data-type="majority">
                <p class="author" id="b1">AUTHOR NAME</p>
                <p id="b2">Some opinion text</p>
                <p id="b3">Extra CAP content</p>
            </article>
        </section>
        """

        cl_xml_list = [
            {
                "id": 1,
                "type": "majority",
                "xml": """
        <opinion type="majority">
            <author id="b1">UPDATED AUTHOR NAME</author>
            <p id="b2">Updated opinion text</p>
        </opinion>
        """,
            }
        ]

        processed_opinions, changes = self.command.update_cap_html_with_cl_xml(
            cap_html, cl_xml_list
        )

        self.assertEqual(
            len(processed_opinions), 1, "One opinion should be processed"
        )

        majority_opinion = processed_opinions[0]
        self.assertEqual(majority_opinion["type"], "majority")

        majority_soup = BeautifulSoup(majority_opinion["xml"], "xml")

        # Check that CAP content is preserved
        self.assertEqual(
            majority_soup.author.text,
            "AUTHOR NAME",
            "The author name should be preserved from CAP HTML",
        )
        self.assertEqual(
            majority_soup.find("p", id="b2").text,
            "Some opinion text",
            "The opinion text should be preserved from CAP HTML",
        )
        self.assertIsNotNone(
            majority_soup.find("p", id="b3"),
            "Extra CAP content should be preserved",
        )
        self.assertEqual(
            majority_soup.find("p", id="b3").text,
            "Extra CAP content",
            "Extra CAP content should be unchanged",
        )
