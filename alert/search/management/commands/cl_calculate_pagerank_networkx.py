__author__ = 'Krist Jin'

from alert import settings
from alert.search.models import Document
from alert.lib.db_tools import queryset_generator
from alert.lib.solr_core_admin import get_data_dir_location, reload_pagerank_external_file_cache
from django.core.management.base import BaseCommand
import logging
import os
import pwd
import shutil
import sys
import time
import networkx as nx

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    args = '<args>'
    help = 'Calculate pagerank value for every case'
    RESULT_FILE_PATH = get_data_dir_location() + "external_pagerank"
    TEMP_EXTENSION = '.tmp'
    result_file = open(RESULT_FILE_PATH + TEMP_EXTENSION, 'w')

    def do_pagerank(self, verbosity=1, chown=True):
        #####################
        #      Stage I      #
        # Import Data to NX #
        #####################
        sys.stdout.write('Initializing...\n')
        graph_size = Document.objects.all().count()
        citing_graph = nx.DiGraph()
        qs = Document.objects.only(
            'pk',
            'cases_cited',
        )
        case_list = queryset_generator(qs, chunksize=10000)
        case_count = 0
        timings = []
        average_per_s = 0

        # Build up the network graph and a list of all valid ids
        id_list = []
        for source_case in case_list:
            case_count += 1
            if case_count % 100 == 1:
                t1 = time.time()
            if case_count % 100 == 0:
                t2 = time.time()
                timings.append(t2 - t1)
                average_per_s = 100 / (sum(timings) / float(len(timings)))
            sys.stdout.write("\rGenerating networkx graph...{:.0%} ({}/{}, {:.1f}/s)".format(
                case_count * 1.0 / graph_size,
                case_count,
                graph_size,
                average_per_s,
            ))
            sys.stdout.flush()
            for target_case in source_case.cases_cited.values_list('parent_documents__id'):
                citing_graph.add_edge(str(source_case.pk), str(target_case[0]))

            # Save all the keys since they get dropped by networkx in Stage II
            id_list.append(str(source_case.pk))

        ######################
        #      Stage II      #
        # Calculate Pagerank #
        ######################
        if verbosity >= 1:
            sys.stdout.write('\n')
            sys.stdout.write('NetworkX PageRank calculating...')
            sys.stdout.flush()
        pr_result = nx.pagerank(citing_graph)
        if verbosity >= 1:
            sys.stdout.write('Complete!\n')

        ###################
        #    Stage III    #
        # Update Pagerank #
        ###################
        progress = 0
        min_value = min(pr_result.values())
        for id in id_list:
            progress += 1
            try:
                new_pr = pr_result[id]
            except KeyError:
                # NetworkX removes the isolated nodes from the network, but they still need to go into the PR file.
                new_pr = min_value
            self.result_file.write('{}={}\n'.format(id, new_pr))

            if verbosity >= 1:
                sys.stdout.write('\rUpdating Pagerank in external file...{:.0%}'.format(
                    progress * 1.0 / graph_size
                ))
                sys.stdout.flush()

        self.result_file.close()

        if verbosity >= 1:
            sys.stdout.write('\nPageRank calculation finished!')
            sys.stdout.write('See the django log for more details.\n')

        ########################
        #       Stage IV       #
        # Maintenance Routines #
        ########################
        if verbosity >= 1:
            sys.stdout.write('Sorting the temp pagerank file for improved Solr performance...\n')

        # Sort the temp file, creating a new file without the TEMP_EXTENSION value, then delete the temp file.
        os.system('sort -n %s%s > %s' % (self.RESULT_FILE_PATH, self.TEMP_EXTENSION, self.RESULT_FILE_PATH))
        os.remove(self.RESULT_FILE_PATH + self.TEMP_EXTENSION)

        if verbosity >= 1:
            sys.stdout.write('Reloading the external file cache in Solr...\n')
        reload_pagerank_external_file_cache()

        if verbosity >= 1:
            sys.stdout.write('Copying pagerank file to %s, for bulk downloading...\n' % settings.DUMP_DIR)
        shutil.copy(self.RESULT_FILE_PATH, settings.DUMP_DIR)
        if chown:
            user_info = pwd.getpwnam('www-data')
            os.chown(settings.DUMP_DIR + 'external_pagerank', user_info.pw_uid, user_info.pw_gid)

    def handle(self, *args, **options):
        self.do_pagerank(verbosity=int(options.get('verbosity', 1)))
