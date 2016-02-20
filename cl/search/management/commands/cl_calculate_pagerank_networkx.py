import logging
import networkx as nx
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
    """Create a new nx DiGraph and populate it.

    This pulls all of the inter-opinion citations into memory then passes all of
    them to nx's `add_edges_from` method. The alternate way to do this process
    is to iterate over the citations calling `add_edge` on each of them. In
    testing with 12M citations, that's marginally slower, however, the advantage
    is that you don't need to pull all of the citations into memory at once.
    """
    g = nx.DiGraph()
    g.add_edges_from(
        list(OpinionsCited.objects.values_list(
            'citing_opinion',
            'cited_opinion',
        ))
    )
    return g


def make_sorted_pr_file(pr_result, result_file_path):
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
    result_file = open(result_file_path + temp_extension, 'w')

    progress = 0
    min_value = min(pr_result.values())
    for pk in Opinion.objects.values_list('pk', flat=True):
        progress += 1
        try:
            new_pr = pr_result[pk]
        except KeyError:
            # Not all nodes will be in the NX DiGraph, some will have no
            # citations, and so will simply get the min-value.
            new_pr = min_value
        result_file.write('{}={}\n'.format(pk, new_pr))
    result_file.close()

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
        pr_results = nx.pagerank(g)
        make_sorted_pr_file(pr_results, self.RESULT_FILE_PATH)
        reload_pagerank_external_file_cache()
        cp_pr_file_to_bulk_dir(self.RESULT_FILE_PATH, chown)

    def handle(self, *args, **options):
        self.do_pagerank()
