__author__ = 'Krist Jin'

from django.core.management.base import BaseCommand, CommandError
from alert.search.models import Document, Citation, Court
from alert.lib.db_tools import queryset_generator

import sys
import random



class Command(BaseCommand):
    args = '<edge_amount>'
    help = 'Create random citing relations among cases'

    def do_random_citing(self, edge_amount):
        i = 0
        doc_id_list = []
        cite_dict = dict()
        for doc in queryset_generator(Document.objects.only("documentUUID")):
            doc_id_list.append(doc.documentUUID)
            cite_dict[doc.documentUUID] = []

        while i < int(edge_amount):
            sys.stdout.write("\rRandom Citing {!s} times...{:.0%}".format(edge_amount, i * 1.0 / int(edge_amount)))
            sys.stdout.flush()
            source_doc_id = random.choice(doc_id_list)
            target_doc_id = random.choice(doc_id_list)
            source_doc = Document.objects.get(documentUUID=source_doc_id)
            target_doc = Document.objects.get(documentUUID=target_doc_id)
            if source_doc_id == target_doc_id:
                if self.verbosity >= 1:
                    self.stdout.write('source==target.\n')
                continue
            elif target_doc_id in cite_dict[source_doc_id]:
                if self.verbosity >= 1:
                    self.stdout.write('{0:d}->{0:d} exists.\n'.format(source_doc_id, target_doc_id))
                continue
            else:
                if self.verbosity >= 1:
                    self.stdout.write('add a new edge {0:d}->{0:d}\n'.format(source_doc_id, target_doc_id))
                source_doc.citation_count += 1
                source_doc.cases_cited.add(target_doc.citation)
                cite_dict[source_doc_id].append(target_doc_id)
                i += 1
        target_doc.save(index=False)
        source_doc.save(index=False)
        print('\nSuccessfully created %s edges in the citation graph\n' % edge_amount)

    def handle(self, *args, **options):
        try:
            self.verbosity = int(options.get('verbosity', 1))
            self.do_random_citing(args[0])
        except IndexError:
            raise CommandError('You must specify the times of random citing')

