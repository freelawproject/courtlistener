import igraph
import logging
import os
import pwd
import shutil

from cl import settings
from cl.lib.solr_core_admin import get_data_dir, \
    reload_pagerank_external_file_cache
from cl.lib.utils import mkdir_p
from cl.search.models import Opinion, OpinionsCited

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def make_and_populate_nx_graph():
    """Create a new igraph object and populate it.

    This pulls all of the inter-opinion citations into memory then passes all of
    them to igraph as a directed graph.
    """
    g = igraph.Graph(directed=True, edges=list(
        OpinionsCited.objects.values_list(
            'citing_opinion',
            'cited_opinion',
        ))
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
    temp_extension = '.tmp'
    min_value = min(pr_results)
    with open(result_file_path + temp_extension, 'w') as f:
        # pr_results has a score for every value between 0 and our highest
        # opinion id that has citations. Write a file that only contains values
        # matching valid Opinions.
        for pk in Opinion.objects.values_list('pk', flat=True):
            try:
                score = pr_results[pk]
            except IndexError:
                # Happens because some items don't have citations, thus aren't
                # in network.
                score = min_value
            f.write('{}={}\n'.format(pk, score))

    # For improved Solr performance, sort the temp file, creating a new file
    # without the temp_extension value.
    os.system('sort -n %s%s > %s' % (
        result_file_path,
        temp_extension,
        result_file_path,
    ))
    os.remove(result_file_path + temp_extension)


def cp_pr_file_to_bulk_dir(result_file_path, chown):
    """Copy the pagerank file to the bulk data directory for public analysis.
    """
    mkdir_p(settings.BULK_DATA_DIR)  # The dir doesn't always already exist.
    shutil.copy(result_file_path, settings.BULK_DATA_DIR)
    if chown:
        user_info = pwd.getpwnam('www-data')
        os.chown(
            settings.BULK_DATA_DIR + 'external_pagerank',
            user_info.pw_uid,
            user_info.pw_gid,
        )


class Command(BaseCommand):
    args = '<args>'
    help = 'Calculate pagerank value for every case'
    RESULT_FILE_PATH = get_data_dir('collection1') + "external_pagerank"

    def do_pagerank(self, chown=True):
        g = make_and_populate_nx_graph()
        pr_results = g.pagerank()
        make_sorted_pr_file(pr_results, self.RESULT_FILE_PATH)
        reload_pagerank_external_file_cache()
        cp_pr_file_to_bulk_dir(self.RESULT_FILE_PATH, chown)

    def handle(self, *args, **options):
        self.do_pagerank()
