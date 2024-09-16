import os

import igraph
from django.conf import settings

from cl.lib.command_utils import VerboseCommand
from cl.lib.solr_core_admin import get_data_dir
from cl.search.models import Opinion, OpinionsCited


def make_and_populate_nx_graph() -> igraph.Graph:
    """Create a new igraph object and populate it.

    This pulls all of the inter-opinion citations into memory then passes all of
    them to igraph as a directed graph.
    """
    g = igraph.Graph(
        directed=True,
        edges=list(
            OpinionsCited.objects.values_list(
                "citing_opinion", "cited_opinion"
            )
        ),
    )
    return g


def make_sorted_pr_file(pr_results, result_file_path):
    """Convert the pagerank results list into something Solr can use.

    Solr uses a file of the form:

        1=0.387789712299
        2=0.214810626172
        3=0.397399661529

    The IDs must be sorted for performance, and every ID should be listed. This
    function takes the pagerank results and converts them into a file like this,
    using the os's `sort` executable for fastest sorting.
    """
    temp_extension = ".tmp"
    min_value = min(pr_results)
    with open(result_file_path + temp_extension, "w") as f:
        # pr_results has a score for every value between 0 and our highest
        # opinion id that has citations. Write a file that only contains values
        # matching valid Opinions.
        for pk in Opinion.objects.values_list("pk", flat=True):
            try:
                score = pr_results[pk]
            except IndexError:
                # Happens because some items don't have citations, thus aren't
                # in network.
                score = min_value
            f.write(f"{pk}={score}\n")

    # For improved Solr performance, sort the temp file, creating a new file
    # without the temp_extension value.
    os.system(
        f"sort -n {result_file_path}{temp_extension} > {result_file_path}"
    )
    os.remove(result_file_path + temp_extension)


class Command(VerboseCommand):
    args = "<args>"
    help = "Calculate pagerank value for every case"

    @staticmethod
    def do_pagerank():
        g = make_and_populate_nx_graph()
        pr_results = g.pagerank()
        return pr_results

    def handle(self, *args, **options):
        super().handle(*args, **options)
        pr_results = self.do_pagerank()
        pr_dest_dir = settings.SOLR_PAGERANK_DEST_DIR
        make_sorted_pr_file(pr_results, pr_dest_dir)
        normal_dest_dir = f"{get_data_dir('collection1')}external_pagerank"
        print(
            "Pagerank file created at %s. Because of distributed servers, "
            "you may need to copy it to its final destination. Somewhere "
            "like: %s." % (pr_dest_dir, normal_dest_dir)
        )
