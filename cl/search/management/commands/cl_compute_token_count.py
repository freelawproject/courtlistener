from math import ceil

import nh3
import tiktoken
from django.contrib.humanize.templatetags.humanize import intword
from django.db.models import QuerySet

from cl.lib.command_utils import VerboseCommand
from cl.search.models import Opinion, RECAPDocument


def get_recap_random_dataset(
    percentage: float = 0.1,
) -> QuerySet[RECAPDocument]:
    """
    Creates a queryset that retrieves a random sample of RECAPDocuments from
    the database.

    This function utilizes the TABLESAMPLE SYSTEM clause within a raw SQL query
    to efficiently retrieve a random subset of RECAPDocuments from the database.
    The percentage argument specifies the proportion of the table to be sampled.

    Args:
        percentage (float): A floating-point value between 0 and 100(inclusive)
         representing the percentage of documents to sample. Defaults to 0.1.

    Returns:
        A Django QuerySet containing a random sample of RECAPDocument objects.
    """
    return RECAPDocument.objects.raw(
        f"SELECT * FROM search_recapdocument TABLESAMPLE SYSTEM ({percentage}) "
    )


def get_opinions_random_dataset(
    percentage: float = 0.1,
) -> QuerySet[Opinion]:
    """
    Creates a queryset that retrieves a random sample of Opinions from the
    database.

    Args:
        percentage (float): A floating-point value between 0 and 100(inclusive)
         representing the percentage of documents to sample. Defaults to 0.1.

    Returns:
        A Django QuerySet containing a random sample of Opinion objects.
    """
    return Opinion.objects.raw(
        f"SELECT * FROM search_opinion TABLESAMPLE SYSTEM ({percentage}) "
    )


def clean_recap_random_set(data: QuerySet[RECAPDocument]):
    """
    Filters a queryset of RECAPDocuments and yields only documents that meet
    specific criteria.

    This function iterates through the provided queryset and checks each
    document for the presence of the required fields. If all conditions are
    met, the document is yielded, making it available for further processing.
    Documents missing any of the criteria are excluded.

    Args:
        data: A Django QuerySet containing RECAPDocuments.

    Yields:
        RECAPDocument objects that meet the following criteria:
            - is_available: The document is marked as available.
            - plain_text: The document contains plain text content.
            - page_count: The document has a valid page count.
    """
    for document in data.iterator():
        if (
            document.is_available
            and document.plain_text
            and document.page_count
        ):
            yield document


def get_token_count_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(string))
    return num_tokens


def get_clean_opinion_text(opinion: Opinion) -> str:
    """
    Extracts and cleans the opinion text from a provided Opinion object.

    This function attempts to retrieve the opinion text from various source
    fields within the Opinion object, prioritizing HTML formats with citations
    over plain text. The supported source fields are:

        - html_with_citations (preferred)
        - html_columbia
        - html_lawbox
        - xml_harvard
        - html_anon_2020
        - html

    If no HTML text is found, the function falls back to the plain_text field.

    The retrieved text is then cleaned using the `nh3.clean`. This cleaning
    process removes all HTML tags while preserving the content.

    Args:
        opinion (Opinion): An object containing the opinion data.

    Returns:
        str: The cleaned opinion text without any HTML tags.
    """
    text = None
    if opinion.html_with_citations:
        text = opinion.html_with_citations
    elif opinion.html_columbia:
        text = opinion.html_columbia
    elif opinion.html_lawbox:
        text = opinion.html_lawbox
    elif opinion.xml_harvard:
        text = opinion.xml_harvard
    elif opinion.html_anon_2020:
        text = opinion.html_anon_2020
    elif opinion.html:
        text = opinion.html

    if not text:
        return opinion.plain_text

    return nh3.clean(text, tags=set())


def compute_avg_from_list(array: list[float]) -> float:
    """
    Computes the average of a list of numbers.

    Args:
        array (list[float]): A list containing numeric values.

    Returns:
        float: The average of the numbers in the list as a floating-point
         value. If the list is empty, returns 0.0.
    """
    return sum(array) / len(array)


class Command(VerboseCommand):
    help = "Compute token count for Recap Documents and Caselaw."

    def add_arguments(self, parser):
        parser.add_argument(
            "--percentage",
            type=float,
            default=0.1,
            help="specifies the proportion of the table to be sampled",
        )

    def handle(self, *args, **options):
        percentage = options["percentage"]
        rd_queryset = get_recap_random_dataset(percentage)

        token_count = []
        tokens_per_page = []
        words_per_page = []
        self.stdout.write("Starting to retrieve the random RECAP dataset.")
        for document in clean_recap_random_set(rd_queryset):
            count = get_token_count_from_string(document.plain_text)
            token_count.append(count)
            tokens_per_page.append(count / document.page_count)
            word_count = len(document.plain_text.split())
            words_per_page.append(ceil(word_count / document.page_count))

        self.stdout.write("Computing averages.")
        sample_size = len(token_count)
        avg_tokens_per_doc = compute_avg_from_list(token_count)
        avg_words_per_page = compute_avg_from_list(words_per_page)
        avg_tokens_per_page = compute_avg_from_list(tokens_per_page)

        self.stdout.write(
            "Counting the total number of document in the Archive."
        )
        total_recap_documents = RECAPDocument.objects.all().count()
        total_token_in_recap = avg_tokens_per_doc * total_recap_documents

        self.stdout.write(f"Size of the dataset: {sample_size}")
        self.stdout.write(f"Average tokens per document: {avg_tokens_per_doc}")
        self.stdout.write(f"Average words per page: {avg_words_per_page}")
        self.stdout.write(f"Average tokens per page: {avg_tokens_per_page}")
        self.stdout.write("-" * 20)
        self.stdout.write(
            f"Total number of recap documents: {total_recap_documents}"
        )
        self.stdout.write(
            f"The sample represents {sample_size/total_recap_documents:.3%} of the Archive"
        )
        self.stdout.write(
            f"Total number of tokens in the recap archive: {intword(total_token_in_recap)}"
        )

        opinion_queryset = get_opinions_random_dataset(percentage)
        self.stdout.write("Starting to retrieve the random Opinion dataset.")
        for opinion in opinion_queryset.iterator():
            text = get_clean_opinion_text(opinion)
            count = get_token_count_from_string(text)
            token_count.append(count)

        self.stdout.write("Computing averages.")
        sample_size = len(token_count)
        avg_tokens_per_opinion = compute_avg_from_list(token_count)

        self.stdout.write(
            "Counting the total number of Opinions in the Archive."
        )
        total_opinions = Opinion.objects.all().count()
        total_token_in_caselaw = avg_tokens_per_opinion * total_opinions

        self.stdout.write(f"Size of the dataset: {len(token_count)}")
        self.stdout.write(
            f"Average tokens per opinion: {avg_tokens_per_opinion}"
        )
        self.stdout.write("-" * 20)
        self.stdout.write(f"Total number of opinions: {total_opinions}")
        self.stdout.write(
            f"The sample represents {sample_size/total_opinions:.3%} of the Caselaw"
        )
        self.stdout.write(
            f"Total number of tokens in caselaw: {intword(total_token_in_caselaw)}"
        )
