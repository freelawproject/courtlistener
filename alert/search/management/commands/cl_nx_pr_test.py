__author__ = 'Krist Jin'

from alert.search.models import Document
from alert.lib.db_tools import queryset_generator
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
        ngraph = nx.DiGraph()
        d = Document.objects.all().order_by('date_filed')[0].date_filed
        qs = Document.objects.only(
            'documentUUID',
            'date_filed',
            'cases_cited',
            )
        case_list = queryset_generator(qs, chunksize=10000)
        case_count = 0
        timings = []
        average_per_s = 0
        for source_case in case_list:
            case_count += 1
            if case_count % 100 == 1:
                t1 = time.time()
            if case_count % 100 == 0:
                t2 = time.time()
                timings.append(t2 - t1)
                average_per_s = 100 / (sum(timings) / float(len(timings)))
            sys.stdout.write("\rGenerating relation file...{:.0%} ({}/{}, {:.1f}/s) at {:<9}".format(
                case_count * 1.0 / graph_size,
                case_count,
                graph_size,
                average_per_s,
                size(sys.getsizeof(ngraph)),
                ))
            sys.stdout.flush()
            for target_case in source_case.cases_cited.values_list('document__pk'):
                ngraph.add_edge(str(source_case.documentUUID), str(target_case[0]))

        if verbosity >= 1:
            sys.stdout.write('\n')
            sys.stdout.write('NetworkX PageRank calculating...\n')
        pr_result = nx.pagerank(ngraph)

        #####################
        #     Stage III     #
        # Update everything #
        #####################
        progress = 0
        for id, pr in pr_result.iteritems():
            progress += 1
            result_file.write(str(id) + '\t' + str(pr) + '\n')
            sys.stdout.write('\rRecording results...{:.0%}'.format(progress * 1.0 / len(pr_result)))
            sys.stdout.flush()
        sys.stdout.write('\n')
        # if verbosity >= 1:
        #     sys.stdout.write('\nPageRank calculation finished! Updated {0:d} cases\n'.format(update_count))
        #     sys.stdout.write('See the django log for more details.\n')
        result_file.close()

    def handle(self, *args, **options):
        self.do_pagerank(verbosity=int(options.get('verbosity', 1)))
