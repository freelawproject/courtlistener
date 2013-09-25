__author__ = 'Krist Jin'

from django.core.management.base import BaseCommand
from alert.search.models import Document
from alert.lib.db_tools import queryset_generator
import logging
import sys

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    args = '<args>'
    help = 'Calculate pagerank value for every case'

    def do_pagerank(self):
        DAMPING_FACTOR = 0.85
        MAX_ITERATIONS = 100
        MIN_DELTA = 0.00001

        sys.stdout.write('Initializing...\n')
        graph_size = Document.objects.all().count()
        min_value = (1.0 - DAMPING_FACTOR)
        doc_dict = {}
        case_list = queryset_generator(
            Document.objects.only(
                "documentUUID",
                "cases_cited",
                "citation",
                "pagerank"
            ).annotate(Count())
        )
        if self.verbosity >= 1:
            sys.stdout.write('graph_size is {0:d}.\n'.format(graph_size))

        case_count = 0
        for case in case_list:
            case_count += 1
            sys.stdout.write("\rSaving data from database locally...{:.0%}".format(case_count * 1.0 / graph_size))
            sys.stdout.flush()
            attr_dict = {}
            id = case.documentUUID
            attr_dict['cases_cited_count'] = case.cases_cited.all().count()
            attr_dict['citing_cases_id'] = case.citation.citing_cases.values_list("documentUUID")
            attr_dict['pagerank'] = case.pagerank
            attr_dict['original_pagerank'] = case.pagerank
            doc_dict[id] = attr_dict

        sys.stdout.write('\n')
        i_times = 0
        for i in range(MAX_ITERATIONS):
            diff = 0
            sys.stdout.write("\rPagerank Calculating...{:.0%}".format(i * 1.0 / MAX_ITERATIONS))
            sys.stdout.flush()
            for key, attr_dict in doc_dict.iteritems():
                tmp_pagerank = min_value
                for id in attr_dict['citing_cases_id']:
                    citing_case_dict = doc_dict[id[0]]
                    tmp_pagerank += DAMPING_FACTOR * citing_case_dict['pagerank'] / citing_case_dict['cases_cited_count']
                diff += abs(attr_dict['pagerank'] - tmp_pagerank)
                attr_dict['pagerank'] = tmp_pagerank
            i_times += 1
            if diff < MIN_DELTA:
                break
        sys.stdout.write("\rPagerank Calculating...100%\n")
        sys.stdout.flush()
        if self.verbosity >= 1:
            sys.stdout.write('Iteration amount is {0:d}.\n'.format(i_times))

        case_count = 0
        update_count = 0
        for key, attr_dict in doc_dict.iteritems():
            case_count += 1
            sys.stdout.write("\rUpdating database...{:.0%}".format(case_count * 1.0 / graph_size))
            sys.stdout.flush()
            if self.verbosity >= 1:
                log_file.write("ID: {0}\told pagerank is {1}\tnew pagerank is {2}\n".format(int(key), attr_dict['original_pagerank'], attr_dict['pagerank']))
            if attr_dict['original_pagerank'] != attr_dict['pagerank']:
                Document.objects.filter(pk=key).update(pagerank=attr_dict['pagerank'])
                update_count += 1
        sys.stdout.write('\nPageRank calculation finish! Updated {0:d} cases\n'.format(update_count))
        if self.verbosity >= 1:
            sys.stdout.write('See the log in pagerank.log\n')
            log_file.close()


    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.do_pagerank()



