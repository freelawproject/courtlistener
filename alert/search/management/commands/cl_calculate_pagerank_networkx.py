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

    def do_pagerank(self, verbosity=1):
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
        
        # Build up a database of the old PR values
        pr_db = {}
        try:
            with open(self.RESULT_FILE_PATH, 'r') as old_result_file:
                for line in old_result_file:
                    id, value = line.split('=')
                    pr_db[id] = float(value)
            created_pr_db = True
        except IOError:
            # The old PR file doesn't exist yet.
            sys.stdout.write("Unable to find old PR file at: %s\n" % RESULT_FILE_PATH)
            sys.stdout.write("Will assume all old PR values are zero.\n")
            sys.stdout.flush()
            created_pr_db = False

        # Build up the network graph
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
            if not created_pr_db:
                # This means that the old PR file didn't exist and we need to load it with zeroes.
                pr_db[str(source_case.pk)] = 0

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
        update_count = 0
        min_value = min(pr_result.values())
        UPDATE_THRESHOLD = min_value * 1.0e-05
        for id, old_pr in pr_db.iteritems():
            progress += 1
            try:
                if abs(old_pr - pr_result[id]) > UPDATE_THRESHOLD:
                    # Save only if the diff is large enough
                    update_count += 1
                    logger.info("ID: {0}\told pagerank is {1}\tnew pagerank is {2}\n".format(
                        id,
                        old_pr,
                        pr_result[id]
                    ))
                    self.result_file.write('{}={}\n'.format(id, pr_result[id]))
                else:
                    logger.info("ID: {0}\told pagerank is {1}\tnew pagerank is {2}\n".format(
                        id,
                        old_pr,
                        old_pr
                    ))
                    self.result_file.write('{}={}\n'.format(id, old_pr))
            #Because NetworkX removed the isolated nodes, which will be updated below
            except KeyError:
                if abs(old_pr - min_value) > UPDATE_THRESHOLD:
                    update_count += 1
                    logger.info("ID: {0}\told pagerank is {1}\tnew pagerank is {2}\n".format(
                        id,
                        old_pr,
                        min_value
                    ))
                    self.result_file.write('{}={}\n'.format(id, min_value))
                else:
                    logger.info("ID: {0}\told pagerank is {1}\tnew pagerank is {2}\n".format(
                        id,
                        old_pr,
                        old_pr
                    ))
                    self.result_file.write('{}={}\n'.format(id, old_pr))
            if verbosity >= 1:
                sys.stdout.write('\rUpdating Pagerank in database and external file...{:.0%}'.format(
                    progress * 1.0 / graph_size
                ))
                sys.stdout.flush()

        self.result_file.close()

        if verbosity >= 1:
            sys.stdout.write('\nPageRank calculation finished! Updated {} ({:.0%}) cases\n'.format(
                update_count,
                update_count * 1.0 / graph_size
            ))
            sys.stdout.write('See the django log for more details.\n')

        ########################
        #       Stage IV       #
        # Maintenance Routines #
        ########################
        if verbosity >= 1:
            sys.stdout.write('Sorting the temp pagerank file, for better Solr performance...\n')

        # Sort the temp file, creating a new file without the TEMP_EXTENSION value, then delete the temp file.
        os.system('sort -n %s%s > %s' % (self.RESULT_FILE_PATH, self.TEMP_EXTENSION, self.RESULT_FILE_PATH))
        os.remove(self.RESULT_FILE_PATH + self.TEMP_EXTENSION)

        if verbosity >= 1:
            sys.stdout.write('Reloading the external file cache in Solr...\n')
        reload_pagerank_external_file_cache()

        if verbosity >= 1:
            sys.stdout.write('Copying pagerank file to sata, for bulk downloading...\n')
        shutil.copy(self.RESULT_FILE_PATH, settings.DUMP_DIR)
        www_data_info = pwd.getpwnam('www-data')
        os.chown(settings.DUMP_DIR + 'external_pagerank', www_data_info.pw_uid, www_data_info.pw_gid)

    def handle(self, *args, **options):
        self.do_pagerank(verbosity=int(options.get('verbosity', 1)))
