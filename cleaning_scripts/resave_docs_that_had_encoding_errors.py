import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.search.models import Document

live = False

paths = '''pdf/2004/01/29/ag_der_dillinger-h\xc3\xbcttenwerke_v._united_states.pdf
pdf/2006/02/21/Gonzales_v._O_Centro_Esp\xc3\xadrita_Beneficente_Uni\xc3\xa3o_do_Vegetal.pdf
pdf/2008/03/25/Medell\xc3\xadn_v._Texas_1.pdf
pdf/2008/08/05/Medell\xc3\xadn_v._Texas.pdf
pdf/2008/09/24/USA_v._Cot\xc3\xa9.pdf
pdf/2010/04/19/Nu\xc3\xb1ez_v._Hasty_et_al..pdf
pdf/2010/08/05/Chlo\xc3\xa9_v._Queen_Bee_of_Beverly_Hills_LLC.pdf
pdf/2011/03/22/Bechtel_Do_Brasil_Constru\xc3\xa7\xc3\xb5es_Ltda._v._UEG_Arauc\xc3\xa1ria_Ltda..pdf
pdf/2011/05/02/United_States_v._Cuadrado_Cede\xc3\xb1o_1.pdf
pdf/2011/05/02/United_States_v._Cuadrado_Cede\xc3\xb1o.pdf
pdf/2011/06/03/United_States_v._The_Painting_Known_as_Le_March\xc3\xa9.pdf
pdf/2011/07/05/NML_Capital_Ltd._v._Banco_Central_de_la_Rep\xc3\xbablica_Argentina.pdf
pdf/2012/12/11/norman_douglas_diamond_and_zaida_gole\xc3\xb1a_del_rosario_v._united_states.pdf
pdf/2013/04/10/skanga_energy__marine_ltd._v._petr\xc3\xb3leos_de_venezuela_s.a..pdf
pdf/2013/04/30/magi_xxi_inc._v._stato_della_citt\xc3\xa0_del_vaticano.pdf
pdf/2013/05/06/swann_v._specialtys_caf\xc3\xa9_and_bakery_ca12.pdf'''

paths = paths.split('\n')

paths = [path.split('\\')[0] for path in paths]

for path in paths:
    print "Path is now: %s" % path
    docs = Document.objects.filter(local_path__startswith='path')

    print "%s docs found." % len(docs)

    if live:
        for doc in docs:
            doc.save()

