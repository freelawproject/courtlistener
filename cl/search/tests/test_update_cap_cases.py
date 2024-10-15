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

    # def test_update_cap_html_with_extra_cap_opinion(self):
    #     # Case: CAP HTML includes an data not present in CL XML
    #     cap_html = """
    #     <section class="casebody">
    #         <article class="opinion" data-type="majority">
    #             <p class="author" id="b1">AUTHOR NAME</p>
    #             <p id="b2">Some opinion text</p>
    #         </article>
    #         <article class="opinion" data-type="dissent">
    #             <p class="author" id="b3">DISSENTING JUDGE</p>
    #             <p id="b4">Dissent text</p>
    #         </article>
    #     </section>
    #     """

    #     cl_xml_list = [
    #         {
    #             "id": 1,
    #             "type": "majority",
    #             "xml": """
    #     <opinion type="majority">
    #         <author id="b1">UPDATED AUTHOR NAME</author>
    #         <p id="b2">Updated opinion text</p>
    #     </opinion>
    #     """,
    #         }
    #     ]

    #     processed_opinions, changes = self.command.update_cap_html_with_cl_xml(
    #         cap_html, cl_xml_list
    #     )

    #     # Check the number of processed opinions
    #     self.assertEqual(
    #         len(processed_opinions), 2, "Both opinions should be processed"
    #     )

    #     # Check that both majority and dissent opinions are in the processed opinions
    #     opinion_types = [op["type"] for op in processed_opinions]
    #     self.assertIn(
    #         "majority",
    #         opinion_types,
    #         "The majority opinion should be in the processed opinions",
    #     )
    #     self.assertIn(
    #         "dissent",
    #         opinion_types,
    #         "The dissent opinion should be in the processed opinions",
    #     )

    #     # Check the content of the majority opinion
    #     majority_opinion = next(
    #         op for op in processed_opinions if op["type"] == "majority"
    #     )
    #     majority_soup = BeautifulSoup(majority_opinion["xml"], "xml")
    #     self.assertEqual(
    #         majority_soup.author.text,
    #         "UPDATED AUTHOR NAME",
    #         "The author name should be updated from CL XML",
    #     )
    #     self.assertEqual(
    #         majority_soup.p.text,
    #         "Updated opinion text",
    #         "The opinion text should be updated from CL XML",
    #     )

    #     # Check the content of the dissent opinion
    #     dissent_opinion = next(
    #         op for op in processed_opinions if op["type"] == "dissent"
    #     )
    #     dissent_soup = BeautifulSoup(dissent_opinion["xml"], "xml")
    #     self.assertEqual(
    #         dissent_soup.author.text,
    #         "DISSENTING JUDGE",
    #         "The dissent author should be preserved from CAP HTML",
    #     )
    #     self.assertEqual(
    #         dissent_soup.p.text,
    #         "Dissent text",
    #         "The dissent text should be preserved from CAP HTML",
    #     )

    #     # Check that changes reflect the update to the majority opinion
    #     self.assertIn("Updated content for majority opinion", changes)

    #     # Check that there's a note about preserving the dissent opinion
    #     self.assertIn("Preserved dissent opinion from CAP HTML", changes)

    # def test_update_cap_html_with_extra_cap_content(self):
    #     # Case: CAP HTML includes extra content within a matching opinion
    #     cap_html = """
    #     <section class="casebody">
    #         <article class="opinion" data-type="majority">
    #             <p class="author" id="b1">AUTHOR NAME</p>
    #             <p id="b2">Some opinion text</p>
    #             <p id="b3">Extra CAP content</p>
    #         </article>
    #     </section>
    #     """

    #     cl_xml_list = [
    #         {
    #             "id": 1,
    #             "type": "majority",
    #             "xml": """
    #     <opinion type="majority">
    #         <author id="b1">UPDATED AUTHOR NAME</author>
    #         <p id="b2">Updated opinion text</p>
    #     </opinion>
    #     """,
    #         }
    #     ]

    #     processed_opinions, changes = self.command.update_cap_html_with_cl_xml(
    #         cap_html, cl_xml_list
    #     )

    #     self.assertEqual(
    #         len(processed_opinions), 1, "One opinion should be processed"
    #     )

    #     majority_opinion = processed_opinions[0]
    #     self.assertEqual(majority_opinion["type"], "majority")

    #     majority_soup = BeautifulSoup(majority_opinion["xml"], "xml")

    #     # Check that CL updates are applied
    #     self.assertEqual(
    #         majority_soup.author.text,
    #         "UPDATED AUTHOR NAME",
    #         "The author name should be updated from CL XML",
    #     )
    #     self.assertEqual(
    #         majority_soup.find("p", id="b2").text,
    #         "Updated opinion text",
    #         "The opinion text should be updated from CL XML",
    #     )

    #     # Check that extra CAP content is preserved
    #     self.assertIsNotNone(
    #         majority_soup.find("p", id="b3"),
    #         "Extra CAP content should be preserved",
    #     )
    #     self.assertEqual(
    #         majority_soup.find("p", id="b3").text,
    #         "Extra CAP content",
    #         "Extra CAP content should be unchanged",
    #     )

    #     # Check that changes reflect the update to the majority opinion and preservation of extra content
    #     self.assertIn("Updated content for majority opinion", changes)
    #     self.assertIn(
    #         "Preserved extra content in majority opinion from CAP HTML",
    #         changes,
    #     )
