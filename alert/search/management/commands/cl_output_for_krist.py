__author__ = 'Krist Jin'

from django.core.management.base import BaseCommand
from alert.search.models import Document
from alert.lib.db_tools import queryset_generator

import sys
import time


class Command(BaseCommand):

    def output_citing_relation(self):
        out_file = open('citing_relation_for_krist.txt', 'w')
        graph_size = Document.objects.all().count()

        qs = Document.objects.only(
            'documentUUID',
            'cases_cited',
            'citation',
        ).prefetch_related(
            'citation__citing_cases'
        )
        case_list = queryset_generator(qs, chunksize=10000)
        case_count = 0
        timings = []
        average_per_s = 0
        for target_case in case_list:
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

            out_file.write('{}\t{}\t'.format(target_case.documentUUID, target_case.cases_cited.count()))
            for source_case_id in target_case.citation.citing_cases.values_list("pk"):
                out_file.write('{}\t'.format(source_case_id[0]))
            out_file.write('\n')

        out_file.close()
        sys.stdout.write('\n')

    def handle(self, *args, **options):
        self.output_citing_relation()
