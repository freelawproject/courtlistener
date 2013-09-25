__author__ = 'Krist Jin'

from django.core.management.base import BaseCommand, CommandError
from alert.search.models import Citation, Document, Court
from alert.lib.db_tools import queryset_generator
import sys

class Command(BaseCommand):
    args = '<args>'
    help = 'Calculate pagerank value for every case'

    def do_pagerank(self):
        DAMPING_FACTOR = 0.85
        MAX_ITERATIONS = 100
        MIN_DELTA = 0.00001

        print('Initializing...')
        graph_size = Document.objects.all().count()
        min_value = (1.0 - DAMPING_FACTOR)
        doc_dict = dict()
        case_list = queryset_generator(Document.objects.only("documentUUID", "cases_cited", "citation", "pagerank"))
        # in case of calling the do_pagerank function in other function (like in the test.py)
        try:
            self.verbosity
        except AttributeError:
            self.verbosity = 1
            sys.stdout.write('verbosity is set to 1 by default\n')
        if self.verbosity >= 1:
            sys.stdout.write('graph_size is {0:d}.\n'.format(graph_size))
            log_file = open('pagerank.log', 'w')

        case_count = 0
        for case in case_list:
            case_count += 1
            sys.stdout.write("\rSaving data from database locally...{:.0%}".format(case_count * 1.0 / graph_size))
            sys.stdout.flush()
            attr_dict = dict()
            id = case.documentUUID
            attr_dict['cases_cited_count'] = case.cases_cited.all().count()
            attr_dict['citing_cases_id'] = case.citation.citing_cases.values_list("documentUUID")
            attr_dict['pagerank'] = case.pagerank
            attr_dict['original_pagerank'] = case.pagerank
            doc_dict[id] = attr_dict

        print('')
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
        print('\nPageRank calculation finish! Updated {0:d} cases'.format(update_count))
        if self.verbosity >= 1:
            sys.stdout.write('See the log in pagerank.log\n')
            log_file.close()


    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.do_pagerank()



