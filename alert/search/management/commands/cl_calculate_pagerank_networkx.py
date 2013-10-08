__author__ = 'Krist Jin'

from alert.search.models import Document
from alert.lib.filesize import size
from django.core.management.base import BaseCommand
import logging
import sys
import time
import networkx as nx

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    args = '<args>'
    help = 'Calculate pagerank value for every case'

    def do_pagerank(self, verbosity=1):
        sys.stdout.write('Initializing...\n')
        graph_size = Document.objects.all().count()
        result_file = open('pr_result.txt', 'w')

        ##########################
        #        Stage I         #
        # Build a Data Structure #
        ##########################
        case_list = Document.objects.only(
            'documentUUID',
            'date_filed',
            'cases_cited',
            'pagerank',
        ).iterator()

        if verbosity >= 1:
            sys.stdout.write('graph_size is {0:d} nodes.\n'.format(graph_size))

        case_count = 0
        doc_dict = {}
        timings = []
        average_per_s = 0
        for case in case_list:
            case_count += 1
            if verbosity >= 1:
                if case_count % 100 == 1:
                    t1 = time.time()
                if case_count % 100 == 0:
                    t2 = time.time()
                    timings.append(t2 - t1)
                    average_per_s = 100 / (sum(timings) / float(len(timings)))
                sys.stdout.write("\rGenerating data in memory...{:.0%} ({}/{}, {:.1f}/s) at {:<9}".format(
                    case_count * 1.0 / graph_size,
                    case_count,
                    graph_size,
                    average_per_s,
                    size(sys.getsizeof(doc_dict)),
                ))
                sys.stdout.flush()
            doc_dict[case.pk] = {
                'pk': case.pk,
                'pagerank': case.pagerank,
                'cached_pagerank': case.pagerank,
                'cases_cited': case.cases_cited.values_list('document__pk'),
            }
        if verbosity >= 1:
            sys.stdout.write('\n')

        ######################
        #      Stage II      #
        # Calculate PageRank #
        ######################
        graph = nx.DiGraph()
        case_count = 0
        for key, case in doc_dict.iteritems():
            case_count += 1
            sys.stdout.write('\rImport citing relation into NetworkX graph...{:.0%}'.format(
                case_count * 1.0 / graph_size))
            sys.stdout.flush()
            source_id = key
            for item in case['cases_cited']:
                target_id = item[0]
                graph.add_edge(source_id, target_id)
        if verbosity >= 1:
            sys.stdout.write('\n')
            sys.stdout.write('NetworkX PageRank calculating...\n')
        pr_result = nx.pagerank(graph)

        #####################
        #     Stage III     #
        # Update everything #
        #####################
        case_count = 0
        update_count = 0
        for key, case in doc_dict.iteritems():
            try:
                case['pagerank'] = pr_result[key]
            except KeyError:
                case['pagerank'] = 0
            case_count += 1
            if verbosity >= 1:
                sys.stdout.write("\rUpdating database...{:.0%}".format(case_count * 1.0 / graph_size))
                sys.stdout.flush()
            logger.info("ID: {0}\told pagerank is {1}\tnew pagerank is {2}\n".format(
                case['pk'],
                case['cached_pagerank'],
                case['pagerank']
            ))
            result_file.write("{0}\t{1}\n".format(case['pk'], case['pagerank']))
            if case['cached_pagerank'] != case['pagerank']:
                # Only save if we have changed the value
                Document.objects.filter(pk=key).update(pagerank=case['pagerank'])
                update_count += 1

        if verbosity >= 1:
            sys.stdout.write('\nPageRank calculation finished! Updated {0:d} cases\n'.format(update_count))
            sys.stdout.write('See the django log for more details.\n')
        result_file.close()

    def handle(self, *args, **options):
        self.do_pagerank(verbosity=int(options.get('verbosity', 1)))
