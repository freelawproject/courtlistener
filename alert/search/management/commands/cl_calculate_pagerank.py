__author__ = 'Krist Jin'

from django.core.management.base import BaseCommand, CommandError
from alert.search.models import Document, Citation, Court
import random

class Command(BaseCommand):
    args = '<args>'
    help = 'Calculate pagerank value for every case'

    def handle(self, *args, **options):
        DAMPING_FACTOR = 0.85
        MAX_ITERATIONS = 100
        MIN_DELTA = 0.00001
        graph_size = Document.objects.all().count()
        min_value = 1.0-DAMPING_FACTOR
        case_list = []

        for case in Document.objects.all():
            case_list.append(case)

        for case in case_list:
            case.pagerank = 1.0
            case.save(index=False)

        for i in range(MAX_ITERATIONS):
            diff = 0
            self.stdout.write("No."+str(i)+" iteration...("+str(MAX_ITERATIONS)+" times at most)\n")
            for case in case_list:
                tmp_pagerank = min_value
                for citing_case in case.citation.citing_cases.all():
                    tmp_pagerank += DAMPING_FACTOR * citing_case.pagerank / len(citing_case.cases_cited.all())
                diff += abs(case.pagerank - tmp_pagerank)
                case.pagerank = tmp_pagerank
                case.save(index=False)
            if diff < MIN_DELTA:
                break

        self.stdout.write('Saving...\n')
        for case in case_list:
            print(str(case.pk)+":\t"+str(case.pagerank))
            case.save(index=True)
        self.stdout.write('PageRank calculation finish!\n')