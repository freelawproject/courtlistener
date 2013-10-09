__author__ = 'Krist Jin'

from django.core.management.base import BaseCommand
from alert.search.models import Document
from alert.lib.db_tools import queryset_generator

import sys
import time


class Command(BaseCommand):

    def output_citing_relation(self):
        out_file = open('citing_relation.txt', 'w')
        graph_size = Document.objects.all().count()

        qs = Document.objects.only(
            'documentUUID',
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
            sys.stdout.write("\rGenerating relation file...{:.0%} ({}/{}, {:.1f}/s)".format(
                case_count * 1.0 / graph_size,
                case_count,
                graph_size,
                average_per_s,
            ))
            sys.stdout.flush()
            for target_case in source_case.cases_cited.values_list('document__pk'):
                out_file.write(str(source_case.documentUUID)
                    + '\t' + str(target_case[0]) + '\n')

        out_file.close()

    def handle(self, *args, **options):
        self.output_citing_relation()
