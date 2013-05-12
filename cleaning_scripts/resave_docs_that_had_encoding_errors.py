import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.search.models import Document

live = False

paths = '''pdf/2004/01/29/ag_der_dillinger-h
pdf/2006/02/21/Gonzales_v._O_Centro_Esp
pdf/2008/03/25/Medell
pdf/2008/09/24/USA_v._Cot
pdf/2010/04/19/Nu
pdf/2010/08/05/Chlo
pdf/2011/03/22/Bechtel_Do_Brasil_Constru
pdf/2011/05/02/United_States_v._Cuadrado_Ced
pdf/2011/06/03/United_States_v._The_Painting_Known_as_Le_March
pdf/2011/07/05/NML_Capital_Ltd._v._Banco_Central_de_la_Rep
pdf/2012/12/11/norman_douglas_diamond_and_zaida_gole'''

paths = paths.split('\n')

for path in paths:
    repr(path)
    print "Path is now: %s" % path
    docs = Document.objects.filter(local_path__startswith='path')

    print "%s docs found." % len(docs)

    if live:
        for doc in docs:
            doc.save()

