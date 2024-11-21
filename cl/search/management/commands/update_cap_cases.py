import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import boto3
from bs4 import BeautifulSoup
from django.conf import settings

from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Opinion, OpinionCluster


class Command(VerboseCommand):
    help = "Update CL cases with the latest CAP data.  Requires crosswalk files to be generated first."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.s3_client = None
        self.bucket_name = None
        self.crosswalk_dir = None
        self.max_workers = None

    def add_arguments(self, parser):
        """Add command line arguments to the parser.

        :param parser: The argument parser
        :type parser: argparse.ArgumentParser
        """
        parser.add_argument(
            "--reporter",
            type=str,
            help="Specific reporter to update (e.g., 'A_2d'). If not provided, all reporters will be processed.",
            required=False,
        )
        parser.add_argument(
            "--crosswalk-dir",
            type=str,
            help="Directory for reading crosswalk files",
            required=True,
        )
        parser.add_argument(
            "--max-workers",
            type=int,
            help="Maximum number of worker threads (default: 4, max: 16)",
            default=4,
        )

    def handle(self, *args, **options):
        """Handle the command execution.

        :param args: Additional arguments
        :param options: Command options
        :type options: Dict[str, Any]
        """
        self.crosswalk_dir = options.get("crosswalk_dir")
        self.max_workers = min(options.get("max_workers"), 16)
        self.setup_s3_client()

        reporter: str | None = options.get("reporter")

        if reporter:
            reporter = reporter.replace(" ", "_").replace(".", "_")
            self.process_crosswalk(reporter)
        else:
            self.process_all_crosswalks()

    def setup_s3_client(self, mock_client: Optional[Any] = None) -> None:
        """Set up S3 client for accessing CAP data in R2.

        :param mock_client: Optional mock client for testing.
        :return: None
        """
        if mock_client:
            self.s3_client = mock_client
        else:
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=settings.CAP_R2_ENDPOINT_URL,
                aws_access_key_id=settings.CAP_R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.CAP_R2_SECRET_ACCESS_KEY,
            )
        self.bucket_name = settings.CAP_R2_BUCKET_NAME

    def process_all_crosswalks(self):
        """Process all crosswalk files in the specified directory concurrently.

        This function scans the 'crosswalk_dir' for all JSON files and processes
        each file using a thread pool to improve performance. It uses a
        ThreadPoolExecutor to handle multiple files concurrently, with the default
        number of worker threads set to 4, and a maximum of 16.

        Errors encountered during processing are logged for debugging purposes.

        Raises:
            Exception: If an error occurs during the processing of a crosswalk file,
            it is caught and logged, but not re-raised.
        """
        crosswalk_files = list(Path(self.crosswalk_dir).glob("*.json"))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.process_crosswalk, file.stem)
                for file in crosswalk_files
            }

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error processing crosswalk: {str(e)}")

    def process_crosswalk(self, reporter: str):
        """Process a single crosswalk file for the given reporter.

        This function reads the crosswalk JSON file for the specified reporter,
        fetches the corresponding CAP HTML and CL XML data, and updates the CL
        XML with changes from the CAP HTML. It also updates the cluster's
        headmatter if changes are detected.

        :param reporter: The reporter to process
        :type reporter: str

        Logs errors encountered during file access or JSON parsing, and warns if
        CAP HTML or CL XML data cannot be fetched. Updates are logged at various
        levels of verbosity.
        """
        crosswalk_path = os.path.join(self.crosswalk_dir, f"{reporter}.json")

        try:
            with open(crosswalk_path, "r") as file:
                crosswalk_data = json.load(file)
        except FileNotFoundError:
            logger.error(f"Crosswalk file not found: {crosswalk_path}")
            return
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in crosswalk file: {crosswalk_path}")
            return

        logger.info(f"Processing file: {crosswalk_path}")

        for entry in crosswalk_data:
            cap_path = entry["cap_path"]
            cl_cluster_id = entry["cl_cluster_id"]

            logger.info(
                f"Processing cluster {cl_cluster_id} with CAP path: {cap_path}"
            )

            cap_html = self.fetch_cap_html(cap_path)
            result = self.fetch_cl_xml(cl_cluster_id)

            if cap_html and result:
                cl_cluster, cl_xml_list = result

                # Process the HTML content directly
                soup = BeautifulSoup(cap_html, "html.parser")
                casebody = soup.find("section", class_="casebody")

                if casebody:
                    processed_opinions, changes_made = (
                        self.update_cap_html_with_cl_xml(
                            str(casebody), cl_xml_list
                        )
                    )

                    self.save_updated_xml(processed_opinions)

                    self.update_cluster_headmatter(cl_cluster_id, soup)
                else:
                    logger.warning(
                        f"No casebody found in CAP HTML for cluster {cl_cluster_id}"
                    )
            else:
                logger.warning(
                    f"Failed to fetch either CAP HTML or CL XML for cluster {cl_cluster_id}"
                )

    def fetch_cap_html(self, cap_path: str) -> Optional[str]:
        """Fetch CAP HTML content from S3.

        :param cap_path: The path to the CAP HTML file in S3
        :type cap_path: str
        :return: The fetched HTML content or None if an error occurred
        :rtype: Optional[str]
        """
        full_s3_path = None
        try:
            # Remove leading slash if present and change extension to .html
            html_path = (
                cap_path.lstrip("/")
                .replace("cases", "html")
                .replace(".json", ".html")
            )
            full_s3_path = f"s3://{self.bucket_name}/{html_path}"
            logger.debug(f"Attempting to fetch: {full_s3_path}")

            response = self.s3_client.get_object(
                Bucket=self.bucket_name, Key=html_path
            )
            return response["Body"].read().decode("utf-8")
        except self.s3_client.exceptions.NoSuchKey:
            logger.error(f"File not found in S3: {full_s3_path}")
        except Exception as e:
            logger.error(f"Error fetching CAP HTML: {str(e)}")
        return None

    def fetch_cl_xml(
        self, cluster_id: int
    ) -> Optional[Tuple[OpinionCluster, List[Dict[str, Any]]]]:
        """Fetch CL XML content for a given cluster ID.

        :param cluster_id: The ID of the opinion cluster
        :type cluster_id: int
        :return: A tuple containing the OpinionCluster and a list of dictionaries containing opinion data, or None if an error occurred
        :rtype: Optional[Tuple[OpinionCluster, List[Dict[str, str]]]]
        """
        try:
            cl_cluster = OpinionCluster.objects.get(id=cluster_id)

            xml_data = []
            for opinion in cl_cluster.sub_opinions.all():
                xml_data.append(
                    {
                        "id": opinion.id,
                        "type": opinion.type,
                        "xml": opinion.xml_harvard,
                    }
                )
            logger.info(
                f"Successfully fetched XML for cluster {cluster_id} ({len(xml_data)} opinions)"
            )
            return cl_cluster, xml_data
        except OpinionCluster.DoesNotExist:
            logger.error(f"OpinionCluster with id {cluster_id} does not exist")
            return None
        except Exception as e:
            logger.error(
                f"Error fetching XML for cluster {cluster_id}: {str(e)}"
            )
            return None

    def rollback_pagination(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Rollback pagination changes to original xml structure

        Convert <span> tags with class 'star-pagination' back to <page-number> tags
        and remove the 'class' attribute. See fix_pagination() in harvard_merge.py

        :param soup: The content to clean up
        :return: soup
        """
        for span in soup.find_all("span", class_="star-pagination"):
            span.name = "page-number"
            # Remove the 'class' attribute
            if "class" in span:
                del span["class"]
            # Restore the 'label' and 'citation-index' attributes (if present)
            if "label" in span.attrs:
                span["label"] = span["label"]
            if "citation-index" in span.attrs:
                span["citation-index"] = span["citation-index"]
            # Restore the content without surrounding spaces or newlines
            if span.string:
                span.string = span.string.strip()
        return soup

    def rollback_footnotes(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Revert footnotes and footnotemarks to their original format

        See fix_footnotes() in harvard_merge.py

        :param soup: Bs4 object containing the modified footnotes
        :return: Content reverted to original footnotes and footnotemarks
        """
        # Revert <a> elements with footnote class to <footnotemark>
        for fn in soup.find_all("a", class_="footnote"):
            fn.name = "footnotemark"
            fn.string = fn.get(
                "label", fn.get("id", "").lstrip("fn").rstrip("_ref")
            )
            for attr in ["href", "id", "class", "label"]:
                if attr in fn.attrs:
                    del fn[attr]

        # Revert <div> elements with footnote class to <footnote>
        for fnl in soup.find_all("div", class_="footnote"):
            label = fnl["id"].lstrip("fn")
            fnl.name = "footnote"
            fnl["label"] = label
            del fnl["id"], fnl["class"]

            # Ensure only <p> tags remain as children
            for child in fnl.contents:
                if child.name == "a":  # Remove unnecessary <a> tags
                    child.decompose()

        # Remove the wrapping <div class="footnotes">
        footnotes_div = soup.find("div", class_="footnotes")
        if footnotes_div:
            # Extract children (footnote divs) and append back to the correct parent
            parent = soup.find("opinion") or soup.find("casebody")
            if parent:
                for child in footnotes_div.find_all("footnote"):
                    parent.append(child.extract())
            footnotes_div.decompose()

        # Remove any empty <footnotemark> tags in footnotes
        for footnote in soup.find_all("footnote"):
            for empty_mark in footnote.find_all("footnotemark"):
                if not empty_mark.get_text(strip=True):
                    empty_mark.decompose()

        return soup

    def update_cap_html_with_cl_xml(
        self, cap_html: str, cl_xml_list: List[Dict[str, str]]
    ) -> Tuple[List[Dict[str, str]], List[str]]:
        """Update CAP HTML content with CL XML information.

        :param cap_html: The CAP HTML content
        :type cap_html: str
        :param cl_xml_list: A list of dictionaries containing CL XML data
        :type cl_xml_list: List[Dict[str, str]]
        :return: A tuple containing processed opinions and a list of changes made
        :rtype: Tuple[List[Dict[str, str]], List[str]]
        """
        cap_soup = BeautifulSoup(cap_html, "html.parser")
        processed_opinions = []
        changes_made = []

        for cl_xml in cl_xml_list:
            cl_soup = BeautifulSoup(cl_xml["xml"], "xml")
            # Revert xml to original
            cl_soup = self.rollback_footnotes(cl_soup)
            cl_soup = self.rollback_pagination(cl_soup)
            cl_opinion = cl_soup.find("opinion")

            if cl_opinion is None:
                continue

            opinion_type = cl_opinion.get("type")
            if opinion_type is None:
                continue

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
                    if cl_elem.get("id"):
                        # We need to verify that the element has an id, when
                        # find(id=None) it will return the first element that does not
                        # have an id attribute at all
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
                                if (
                                    attr != "id"
                                    and cap_elem.get(attr) != value
                                ):
                                    cap_elem[attr] = value
                                    changes_made.append(
                                        f"Updated attribute '{attr}' for element {cl_elem.get('id')}"
                                    )
                matching_opinion.replace_with(new_opinion)
                # Convert updated CAP HTML back to XML
                updated_xml = self.convert_html_to_xml(str(new_opinion))
                logger.debug(f"\nUpdated XML for opinion type {opinion_type}:")
                logger.debug(updated_xml)

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

        if changes_made:
            logger.debug("\nChanges made:")
            for change in changes_made:
                logger.debug(f"  - {change}")
        else:
            logger.info("No changes were necessary.")

        return processed_opinions, changes_made

    def convert_html_to_xml(self, html_content: str) -> str:
        """Convert HTML content to XML format.

        This function parses the given HTML content and modifies the tag names
        and attributes based on the class names.

        :param html_content: The HTML content to convert
        :type html_content: str
        :return: The converted XML content as a string
        :rtype: str
        """
        soup = BeautifulSoup(html_content, "html.parser")

        for element in soup.find_all():
            classes = element.get("class", [])

            if len(classes) == 1:
                new_tag = classes[0]
                element.name = new_tag
                del element["class"]
            elif len(classes) > 1:
                element["type"] = " ".join(classes)
                del element["class"]

            for attr, value in element.attrs.items():
                if attr not in ["class", "type"]:
                    element[attr] = value

        for element in soup.find_all():
            if element.string:
                element.string = element.string.strip()

        return str(soup)

    def save_updated_xml(self, processed_opinions: List[Dict[str, str]]):
        """Save the updated XML for processed opinions.

        :param processed_opinions: A list of dictionaries containing processed opinion data
        :type processed_opinions: List[Dict[str, str]]
        """
        for opinion_data in processed_opinions:
            try:
                opinion = Opinion.objects.get(id=opinion_data["id"])
                opinion.xml_harvard = opinion_data["xml"]
                opinion.save()
                logger.info(
                    f"Successfully updated XML for opinion {opinion.id} (type: {opinion_data['type']})"
                )
            except Opinion.DoesNotExist:
                logger.error(
                    f"Opinion with id {opinion_data['id']} does not exist"
                )
            except Exception as e:
                logger.error(
                    f"Error updating XML for opinion {opinion_data['id']}: {str(e)}"
                )

    def update_cluster_headmatter(self, cluster_id: int, soup: BeautifulSoup):
        """Update the headmatter of an OpinionCluster with new data from CAP.

        :param cluster_id: The ID of the opinion cluster to update
        :type cluster_id: int
        :param soup: A BeautifulSoup object containing the parsed CAP HTML
        :type soup: BeautifulSoup
        """
        try:
            cluster = OpinionCluster.objects.get(id=cluster_id)
            head_matter = soup.find("section", class_="head-matter")

            if head_matter:
                # Convert the head-matter to XML
                new_headmatter = self.convert_html_to_xml(str(head_matter))

                if cluster.headmatter != new_headmatter:
                    cluster.headmatter = new_headmatter
                    cluster.save()
                    logger.info(f"Updated headmatter for cluster {cluster_id}")
                else:
                    logger.debug(
                        f"No change in headmatter for cluster {cluster_id}"
                    )
            else:
                logger.warning(
                    f"No head-matter section found in CAP data for cluster {cluster_id}"
                )
        except OpinionCluster.DoesNotExist:
            logger.error(f"OpinionCluster with id {cluster_id} does not exist")
        except Exception as e:
            logger.error(
                f"Error updating headmatter for cluster {cluster_id}: {str(e)}"
            )
