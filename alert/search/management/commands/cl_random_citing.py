__author__ = 'Krist Jin'

from django.core.management.base import BaseCommand, CommandError
from alert.search.models import Document, Citation, Court
from alert.lib.db_tools import queryset_generator

import sys
import random



class Command(BaseCommand):
    args = '<edge_amount>'
    help = 'Create random citing relations among cases'

    def handle(self, *args, **options):
        do_random_citing(args[0])

def do_random_citing(edge_amount):
    i = 0
    doc_id_list = []
    cite_dict = dict()
    for doc in queryset_generator(Document.objects.only("documentUUID")):
        doc_id_list.append(doc.documentUUID)
        cite_dict[doc.documentUUID] = []

    while i < int(edge_amount):
        print(str(i) + ' / ' + str(edge_amount) + '\n')
        sys.stdout.write("\rRandom Citing {!s} times...{:.0%}".format(edge_amount, i*1.0/int(edge_amount)))
        sys.stdout.flush()
        source_doc_id = random.choice(doc_id_list)
        target_doc_id = random.choice(doc_id_list)
        source_doc = Document.objects.get(documentUUID=source_doc_id)
        target_doc = Document.objects.get(documentUUID=target_doc_id)
        if source_doc_id == target_doc_id:
            print('source==target.\n')
            continue
        elif target_doc_id in cite_dict[source_doc_id]:
            print('source->target exists.\n')
            continue
        else:
            source_doc.citation_count += 1
            source_doc.cases_cited.add(target_doc.citation)
            cite_dict[source_doc_id].append(target_doc_id)
            i += 1
    target_doc.save(index=False)
    source_doc.save(index=False)
    print('\nSuccessfully created "%s" edges in the citation graph\n' % edge_amount)