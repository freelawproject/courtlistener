__author__ = 'Krist Jin'

from django.core.management.base import BaseCommand, CommandError
from alert.search.models import Citation
from alert.search.models import Document
from alert.lib.db_tools import queryset_generator
import sys

class Command(BaseCommand):
    args = '<args>'
    help = 'Calculate pagerank value for every case'

    def handle(self, *args, **options):
        do_pagerank()



def do_pagerank():
    DAMPING_FACTOR = 0.85
    MAX_ITERATIONS = 100
    MIN_DELTA = 0.00001

    #graph_size = Document.objects.all().count()
    min_value = (1.0 - DAMPING_FACTOR)
    doc_dict = dict()
    case_list = queryset_generator(Document.objects.only("documentUUID", "cases_cited", "citation", "pagerank"))
    print("Saving data from database locally...")
    for case in case_list:
        attr_dict = dict()
        id = case.documentUUID
        attr_dict['cases_cited_count'] = case.cases_cited.all().count()
        attr_dict['citing_cases_id'] = case.citation.citing_cases.values_list("documentUUID")
        attr_dict['pagerank'] = 1
        doc_dict[id] = attr_dict

    for i in range(MAX_ITERATIONS):
        diff = 0
        #print("No.{:d} iteration...({:d} times at most)".format(i, MAX_ITERATIONS))
        sys.stdout.write("\rPagerank Calculating...{:.0%}".format(i*1.0/MAX_ITERATIONS))
        sys.stdout.flush()
        for key, attr_dict in doc_dict.iteritems():
            tmp_pagerank = min_value
            for id in attr_dict['citing_cases_id']:
                citing_case_dict = doc_dict[id[0]]
                tmp_pagerank += DAMPING_FACTOR * citing_case_dict['pagerank'] / citing_case_dict['cases_cited_count']
            diff += abs(attr_dict['pagerank'] - tmp_pagerank)
            attr_dict['pagerank'] = tmp_pagerank
        if diff < MIN_DELTA:
            break
    sys.stdout.write("\rPagerank Calculating...100%\n")
    sys.stdout.flush()
    print('Updating database...')
    for key, attr_dict in doc_dict.iteritems():
        Document.objects.filter(pk=key).update(pagerank=attr_dict['pagerank'])
        #print(str(key)+":\t"+str(attr_dict['pagerank']))
    print('PageRank calculation finish!')