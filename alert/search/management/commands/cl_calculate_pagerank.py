__author__ = 'Krist Jin'

from alert.search.models import Document
from alert.lib.db_tools import queryset_generator, queryset_generator_by_date
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils.timezone import now, utc, make_aware
import logging
import sys

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    args = '<args>'
    help = 'Calculate pagerank value for every case'

    def do_pagerank(self, verbosity=1):
        DAMPING_FACTOR = 0.85
        MAX_ITERATIONS = 100
        MIN_DELTA = 0.00001

        sys.stdout.write('Initializing...\n')
        graph_size = Document.objects.all().count()
        min_value = (1.0 - DAMPING_FACTOR)

        # Chunk by date for best performance
        d = Document.objects.all().order_by('date_filed')[0].date_filed
        start_date = make_aware(datetime.combine(d, datetime.min.time()), utc)
        end_date = now()
        qs = Document.objects.only(
            'documentUUID',
            'date_filed',
            'cases_cited',
            'citation',
            'pagerank',
        ).prefetch_related(
            'citation__citing_cases'
        ).annotate(
            Count('cases_cited')
        )
        case_list = queryset_generator_by_date(qs, 'date_filed', start_date, end_date, chunksize=100)

        if verbosity >= 1:
            sys.stdout.write('graph_size is {0:d} nodes.\n'.format(graph_size))

        case_count = 0
        doc_dict = {}
        for case in case_list:
            case_count += 1
            if verbosity >= 1:
                sys.stdout.write("\rGenerating data in memory...{:.0%}".format(case_count * 1.0 / graph_size))
                sys.stdout.flush()
            case.citing_cases_ids = case.citation.citing_cases.values_list("pk")
            case.cached_pagerank = case.pagerank
            doc_dict[case.pk] = case

        if verbosity >= 1:
            sys.stdout.write('\n')
        i_times = 0
        for i in range(MAX_ITERATIONS):
            diff = 0
            if verbosity >= 1:
                sys.stdout.write("\rPagerank Calculating...{:.0%}".format(i * 1.0 / MAX_ITERATIONS))
                sys.stdout.flush()
            for key, case in doc_dict.iteritems():
                tmp_pagerank = min_value
                for id in case.citing_cases_ids:
                    citing_case = doc_dict[id[0]]
                    tmp_pagerank += DAMPING_FACTOR * citing_case.pagerank / citing_case.cases_cited__count
                diff += abs(case.pagerank - tmp_pagerank)
                case.pagerank = tmp_pagerank
            i_times += 1
            if diff < MIN_DELTA:
                break
        if verbosity >= 1:
            sys.stdout.write("\rPagerank Calculating...100%\n")
            sys.stdout.flush()
            sys.stdout.write('Iteration count was {0:d}.\n'.format(i_times))

        #####################
        #     Stage II      #
        # Update everything #
        #####################
        case_count = 0
        update_count = 0
        for key, case in doc_dict.iteritems():
            case_count += 1
            if verbosity >= 1:
                sys.stdout.write("\rUpdating database...{:.0%}".format(case_count * 1.0 / graph_size))
                sys.stdout.flush()
            logger.info("ID: {0}\told pagerank is {1}\tnew pagerank is {2}\n".format(
                                                                case.pk, case.cached_pagerank, case.pagerank))
            if case.cached_pagerank != case.pagerank:
                # Only save if we have changed the value
                case.save(index=False).update_fields('pagerank')
                update_count += 1

        if verbosity >= 1:
            sys.stdout.write('\nPageRank calculation finished! Updated {0:d} cases\n'.format(update_count))
            sys.stdout.write('See the django log for more details.\n')

    def handle(self, *args, **options):
        self.do_pagerank(verbosity=int(options.get('verbosity', 1)))



