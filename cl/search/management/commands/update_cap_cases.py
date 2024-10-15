import json
import os
import boto3
from django.core.management.base import BaseCommand
from django.conf import settings
from cl.search.models import Opinion, OpinionCluster
import logging
from bs4 import BeautifulSoup
from lxml import etree
import re
from django.utils.safestring import mark_safe
import html

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Update CL cases with the latest CAP data using crosswalk files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reporter",
            type=str,
            help="Specific reporter to update (e.g., 'A_2d'). If not provided, all reporters will be processed.",
            required=False,
        )

    def handle(self, *args, **options):
        reporter = options.get("reporter")

        self.setup_s3_client()

        if reporter:
            self.process_crosswalk(reporter)
        else:
            self.process_all_crosswalks()

    def setup_s3_client(self):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.CAP_R2_ENDPOINT_URL,
            aws_access_key_id=settings.CAP_R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.CAP_R2_SECRET_ACCESS_KEY,
        )
        self.bucket_name = settings.CAP_R2_BUCKET_NAME

    def process_all_crosswalks(self):
        crosswalk_dir = "cl/search/crosswalks"
        for filename in os.listdir(crosswalk_dir):
            if filename.endswith(".json"):
                reporter = filename[:-5]  # Remove the .json extension
                self.stdout.write(
                    self.style.SUCCESS(f"Processing reporter: {reporter}")
                )
                self.process_crosswalk(reporter)

    def process_crosswalk(self, reporter):
        crosswalk_path = f"cl/search/crosswalks/{reporter}.json"

        try:
            with open(crosswalk_path, "r") as file:
                crosswalk_data = json.load(file)
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f"Crosswalk file not found: {crosswalk_path}")
            )
            return
        except json.JSONDecodeError:
            self.stdout.write(
                self.style.ERROR(
                    f"Invalid JSON in crosswalk file: {crosswalk_path}"
                )
            )
            return

        for entry in crosswalk_data:
            cap_path = entry["cap_path"]
            cl_cluster_id = entry["cl_cluster_id"]

            self.stdout.write(
                self.style.WARNING(
                    f"Processing cluster {cl_cluster_id} with CAP path: {cap_path}"
                )
            )

            cap_html = self.fetch_cap_html(cap_path)
            cl_xml_list = self.fetch_cl_xml(cl_cluster_id)

            if cap_html and cl_xml_list:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully fetched CAP HTML and CL XML for cluster {cl_cluster_id}"
                    )
                )
                self.stdout.write(
                    self.style.WARNING("\nOriginal CAP HTML Content:\n\n")
                )
                self.stdout.write(cap_html)

                # Update CAP HTML with CL XML information
                processed_opinions, changes = self.update_cap_html_with_cl_xml(
                    cap_html, cl_xml_list
                )

                if processed_opinions:
                    self.save_updated_xml(processed_opinions)

                self.stdout.write(
                    self.style.WARNING("\n\nUpdated CAP HTML Content:\n\n")
                )
                for opinion in processed_opinions:
                    # Check if the opinion XML is not empty
                    if opinion["xml"]:
                        # Unescape the HTML
                        opinion_str = html.unescape(opinion["xml"])

                        # Parse and prettify
                        try:
                            opinion_soup = BeautifulSoup(
                                opinion_str, "html.parser"
                            )
                            pretty_opinion = opinion_soup.prettify()

                            # Write to output
                            self.stdout.write(mark_safe(pretty_opinion))
                            self.stdout.write("\n\n")
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"Error processing opinion XML: {str(e)}"
                                )
                            )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Empty XML for opinion type {opinion['type']}"
                            )
                        )

                self.stdout.write(
                    self.style.WARNING("\n\nCL XML Content:\n\n")
                )
                for opinion in cl_xml_list:
                    self.stdout.write(
                        f"Opinion ID: {opinion['id']}, Type: {opinion['type']}\n"
                    )
                    self.stdout.write(opinion["xml"])
                    self.stdout.write("\n\n")

                if changes:
                    self.stdout.write(self.style.WARNING("Changes made:"))
                    for change in changes:
                        self.stdout.write(f"  - {change}")
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "No changes needed for this document."
                        )
                    )

                # TODO: update cl xml in db
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Failed to fetch either CAP HTML or CL XML for cluster {cl_cluster_id}"
                    )
                )

    def convert_xml_to_html(self, xml_content):
        soup = BeautifulSoup(xml_content, "xml")

        # Convert opinion tags
        for opinion in soup.find_all("opinion"):
            opinion.name = "div"
            opinion["class"] = opinion.get("type", "")

        # Convert author tags
        for author in soup.find_all("author"):
            author.name = "p"
            author["class"] = "author"

        # Convert paragraphs
        for p in soup.find_all("p"):
            p.name = "p"

        return str(soup)

    def fetch_cap_html(self, cap_path):
        try:
            # Remove leading slash if present and change extension to .html
            cap_path = cap_path.lstrip("/")
            html_path = cap_path.replace("cases", "html").replace(
                ".json", ".html"
            )
            # Print the full S3 path for debugging
            full_s3_path = f"s3://{self.bucket_name}/{html_path}"
            self.stdout.write(
                self.style.WARNING(f"Attempting to fetch: {full_s3_path}")
            )

            response = self.s3_client.get_object(
                Bucket=self.bucket_name, Key=html_path
            )
            return response["Body"].read().decode("utf-8")
        except self.s3_client.exceptions.NoSuchKey:
            self.stdout.write(
                self.style.ERROR(f"File not found in S3: {full_s3_path}")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error fetching CAP HTML: {str(e)}")
            )
        return None

    def fetch_cl_xml(self, cluster_id):
        try:
            cluster = OpinionCluster.objects.get(id=cluster_id)
            opinions = Opinion.objects.filter(cluster=cluster)

            xml_data = []
            for opinion in opinions:
                xml_data.append(
                    {
                        "id": opinion.id,
                        "type": opinion.type,
                        "xml": opinion.xml_harvard,
                    }
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully fetched XML for cluster {cluster_id} ({len(xml_data)} opinions)"
                )
            )
            return xml_data
        except OpinionCluster.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"OpinionCluster with id {cluster_id} does not exist"
                )
            )
            return None
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"Error fetching XML for cluster {cluster_id}: {str(e)}"
                )
            )
            return None

    def update_cap_html_with_cl_xml(self, cap_html, cl_xml_list):
        cap_soup = BeautifulSoup(cap_html, "html.parser")
        processed_opinions = []
        changes_made = []

        for cl_xml in cl_xml_list:
            cl_soup = BeautifulSoup(cl_xml["xml"], "xml")
            cl_opinion = cl_soup.find("opinion")

            if cl_opinion is None:
                continue

            opinion_type = cl_opinion.get("type")
            if opinion_type is None:
                continue

            # Find corresponding section in CAP HTML
            matching_opinion = cap_soup.find(
                "article", class_="opinion", attrs={"data-type": opinion_type}
            )

            if matching_opinion:
                # Convert article to opinion tag
                new_opinion = cap_soup.new_tag("opinion")
                new_opinion.attrs = matching_opinion.attrs
                new_opinion["type"] = opinion_type

                # Transfer all content from the original article to the new opinion tag
                new_opinion.extend(matching_opinion.contents)

                # Update all elements with matching IDs
                for cl_elem in cl_opinion.find_all(True):  # Find all elements
                    cap_elem = new_opinion.find(id=cl_elem.get("id"))
                    if cap_elem:
                        # Update tag name if different
                        if cap_elem.name != cl_elem.name:
                            changes_made.append(
                                f"Updated element {cl_elem.get('id')} type from {cap_elem.name} to {cl_elem.name}"
                            )
                            new_elem = cap_soup.new_tag(
                                cl_elem.name, id=cl_elem.get("id")
                            )
                            new_elem.attrs = cap_elem.attrs
                            new_elem.extend(cap_elem.contents)
                            cap_elem.replace_with(new_elem)

                        # Update attributes
                        for attr, value in cl_elem.attrs.items():
                            if attr != "id" and cap_elem.get(attr) != value:
                                cap_elem[attr] = value
                                changes_made.append(
                                    f"Updated attribute '{attr}' for element {cl_elem.get('id')}"
                                )
                print(
                    "Before replacement - matching_opinion:", matching_opinion
                )
                print("Before replacement - new_opinion:", new_opinion)
                matching_opinion.replace_with(new_opinion)
                print("After replacement - new_opinion:", new_opinion)

                print("Before conversion to XML:", str(new_opinion))
                # Convert updated CAP HTML back to XML
                updated_xml = self.convert_html_to_xml(str(new_opinion))
                print("After conversion to XML:", updated_xml)

                self.stdout.write(
                    self.style.WARNING(
                        f"\nUpdated XML for opinion type {opinion_type}:"
                    )
                )
                self.stdout.write(self.style.WARNING(updated_xml))

            else:
                # No matching opinion in CAP HTML, use CL XML as-is
                updated_xml = str(cl_opinion)
                changes_made.append(
                    f"Used existing CL XML for {opinion_type} opinion (no match in CAP HTML)"
                )

            processed_opinions.append(
                {
                    "id": cl_xml["id"],
                    "type": opinion_type,
                    "xml": updated_xml,
                }
            )

        # Log changes
        if changes_made:
            self.stdout.write(self.style.WARNING("\nChanges made:"))
            for change in changes_made:
                self.stdout.write(self.style.WARNING(f"  - {change}"))
        else:
            self.stdout.write(
                self.style.WARNING("\nNo changes were necessary.")
            )

        return processed_opinions, changes_made

    def convert_html_to_xml(self, html_content):
        print("Input to convert_html_to_xml:", html_content)

        soup = BeautifulSoup(html_content, "html.parser")
        root = soup.opinion

        xml_root = etree.Element(root.name)

        for name, value in root.attrs.items():
            if isinstance(value, list):
                xml_root.set(name, " ".join(value))
            else:
                xml_root.set(name, str(value))

        def convert_element(html_elem, xml_parent):
            xml_elem = etree.SubElement(xml_parent, html_elem.name)

            for name, value in html_elem.attrs.items():
                if isinstance(value, list):
                    xml_elem.set(name, " ".join(value))
                else:
                    xml_elem.set(name, str(value))

            if html_elem.string:
                xml_elem.text = html_elem.string.strip()

            # Recursively convert child elements
            for child in html_elem.children:
                if child.name:
                    convert_element(child, xml_elem)

        # Convert the HTML structure to XML
        for child in root.children:
            if child.name:  # Only process tag elements, not strings
                convert_element(child, xml_root)

        # Convert the XML tree to a string
        xml_string = etree.tostring(
            xml_root, encoding="unicode", pretty_print=True
        )

        # Clean up the XML
        xml_string = re.sub(r"\n\s*\n", "\n", xml_string)  # Remove empty lines
        xml_string = re.sub(
            r">\s+<", "><", xml_string
        )  # Remove whitespace between tags

        print("Output from convert_html_to_xml:", xml_string)
        return xml_string

    def save_updated_xml(self, processed_opinions):
        for opinion_data in processed_opinions:
            try:
                opinion = Opinion.objects.get(id=opinion_data["id"])
                opinion.xml_harvard = opinion_data["xml"]
                opinion.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully updated XML for opinion {opinion.id} (type: {opinion_data['type']})"
                    )
                )
            except Opinion.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(
                        f"Opinion with id {opinion_data['id']} does not exist"
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Error updating XML for opinion {opinion_data['id']}: {str(e)}"
                    )
                )
