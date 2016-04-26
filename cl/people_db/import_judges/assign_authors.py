# -*- coding: utf-8 -*-
"""
Created on Fri Mar 18 18:27:09 2016

@author: elliott
"""

from unidecode import unidecode

from cl.corpus_importer.import_columbia.parse_judges import find_judges
from cl.lib.import_lib import find_person
from cl.search.models import OpinionCluster


def assign_authors(testing=False):

    clusters = (OpinionCluster.objects
                .exclude(judges='')
                .select_related('docket__court__id')
                .only('date_filed', 'judges', 'docket__court_id'))
    total = clusters.count()
    i = 0

    for cluster in clusters:
        i += 1
        print u"(%s/%s): Processing: %s, %s" % (i, total, cluster.pk,
                                               cluster.date_filed)
        #print u"  Judge string: %s".encode('utf-8') % cluster.judges

        judgestr = unidecode(cluster.judges)
        print "  Judge string: %s" % judgestr

        if 'curiam' in judgestr.lower():
            opinion = cluster.sub_opinions.all()[0]
            opinion.per_curiam = True
            print u'  Per Curiam assigned.'
            if not testing:
                opinion.save(index=False)
            continue

        #judges = find_judges(cluster.judges)

        judges = find_judges(judgestr)

        if len(judges) == 0:
            continue

        candidates = []
        for judge in judges:
            candidates.append(find_person(judge,
                                          cluster.docket.court_id,
                                          case_date=cluster.date_filed))
        candidates = [c for c in candidates if c is not None]

        if len(candidates) == 0:
            # more than one judge token, but no DB matches
            print u'  No match.'
            continue

        opinion = cluster.sub_opinions.all()[0]

        if len(candidates) == 1 and len(judges) == 1:
            # one judge token, one DB match
            opinion.author = candidates[0]
            print '  Author assigned: %s' % unidecode(str(candidates[0]))
        elif len(candidates) == 1 and len(judges) > 1:
            # multiple judge tokens, one DB match
            opinion.author = candidates[0]
            print u'  Author assigned: %s (with %d missing tokens)' % (
                unidecode(str(candidates[0])),
                len(judges)-1
            )
        else:
            # more than one DB match
            opinion.panel = candidates
            print u'  Panel assigned: %s' % candidates

        if not testing:
            opinion.save(index=False)


