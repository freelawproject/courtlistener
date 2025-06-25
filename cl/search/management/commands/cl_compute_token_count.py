from math import ceil

import nh3
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intword
from django.db.models import QuerySet

from cl.lib.command_utils import VerboseCommand
from cl.lib.string_utils import get_token_count_from_string
from cl.search.models import SEARCH_TYPES, Opinion, RECAPDocument


def get_recap_random_dataset(
    percentage: float = 0.1, db_connection: str = "default"
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
        db_connection (str): The database connection alias to use for the
            query. Defaults to "default".

    Returns:
        A Django QuerySet containing a random sample of RECAPDocument objects.
    """
    return RECAPDocument.objects.using(db_connection).raw(
        f"SELECT * FROM search_recapdocument TABLESAMPLE SYSTEM ({percentage}) "
        "where is_available= True and plain_text <> '' and page_count > 0"
    )


def get_opinions_random_dataset(
    percentage: float = 0.1, db_connection: str = "default"
) -> QuerySet[Opinion]:
    """
    Creates a queryset that retrieves a random sample of Opinions from the
    database.

    Args:
        percentage (float): A floating-point value between 0 and 100(inclusive)
         representing the percentage of documents to sample. Defaults to 0.1.
        db_connection (str): The database connection alias to use for the
            query. Defaults to "default".

    Returns:
        A Django QuerySet containing a random sample of Opinion objects.
    """
    return Opinion.objects.using(db_connection).raw(
        f"SELECT * FROM search_opinion TABLESAMPLE SYSTEM ({percentage}) "
    )


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
            "--type",
            type=str,
            choices=[SEARCH_TYPES.RECAP_DOCUMENT, SEARCH_TYPES.OPINION],
            required=True,
            help=(
                "Specify which dataset to compute token count for: "
                f"({', '.join([SEARCH_TYPES.RECAP_DOCUMENT, SEARCH_TYPES.OPINION])})"
            ),
        )
        parser.add_argument(
            "--percentage",
            type=float,
            default=1.0,
            help=(
                "Specifies the proportion of the table to be sampled (0.0 to "
                "100.0 percent). Defaults to 1.0."
            ),
        )
        parser.add_argument(
            "--use-replica",
            action="store_true",
            default=False,
            help="Use this flag to run the queries in the replica db",
        )

    def _compute_case_law_token_count(
        self, percentage: float, db_connection: str
    ):
        """
        Computes and reports token counts for Caselaw dataset.
        """
        opinion_queryset = get_opinions_random_dataset(
            percentage, db_connection
        )
        self.stdout.write("Starting to retrieve the random Opinion dataset.")
        token_count = []
        words_per_opinion = []
        for opinion in opinion_queryset.iterator():
            text = get_clean_opinion_text(opinion)
            count = get_token_count_from_string(text)
            words_per_opinion.append(len(text.split()))
            token_count.append(count)

        self.stdout.write("Computing averages.")
        sample_size = len(token_count)
        avg_tokens_per_opinion = compute_avg_from_list(token_count)
        avg_words_per_opinion = compute_avg_from_list(words_per_opinion)

        self.stdout.write(
            "Counting the total number of Opinions in the Archive."
        )
        total_opinions = Opinion.objects.using(db_connection).all().count()
        total_token_in_caselaw = avg_tokens_per_opinion * total_opinions

        self.stdout.write(f"Size of the dataset: {len(token_count)}")
        self.stdout.write(
            f"Average tokens per opinion: {avg_tokens_per_opinion}"
        )
        self.stdout.write(
            f"Average words per opinion: {avg_words_per_opinion}"
        )
        self.stdout.write("-" * 20)
        self.stdout.write(f"Total number of opinions: {total_opinions}")
        self.stdout.write(
            f"The sample represents {sample_size / total_opinions:.3%} of the Caselaw"
        )
        self.stdout.write(
            f"Total number of tokens in caselaw: {intword(total_token_in_caselaw)}"
        )

    def _compute_recap_token_count(
        self, percentage: float, db_connection: str
    ):
        """
        Computes and reports token counts for RECAP Documents.
        """
        rd_queryset = get_recap_random_dataset(percentage, db_connection)

        token_count = []
        tokens_per_page = []
        words_per_page = []
        self.stdout.write("Starting to retrieve the random RECAP dataset.")
        for document in rd_queryset.iterator():
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
            "Counting the total number of documents in the Archive."
        )
        total_recap_documents = (
            RECAPDocument.objects.using(db_connection)
            .filter(is_available=True)
            .exclude(plain_text__exact="")
            .all()
            .count()
        )
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
            f"The sample represents {sample_size / total_recap_documents:.3%} of the Archive"
        )
        self.stdout.write(
            f"Total number of tokens in the recap archive: {intword(total_token_in_recap)}"
        )

    def handle(self, *args, **options):
        percentage = options["percentage"]
        db_connection = (
            "replica"
            if options["use_replica"] and "replica" in settings.DATABASES
            else "default"
        )
        dataset_type = options["type"]

        match dataset_type:
            case SEARCH_TYPES.RECAP_DOCUMENT:
                self._compute_recap_token_count(percentage, db_connection)
            case SEARCH_TYPES.OPINION:
                self._compute_case_law_token_count(percentage, db_connection)
            case _:
                raise NotImplementedError(
                    f"Type '{dataset_type}' is not supported."
                )
