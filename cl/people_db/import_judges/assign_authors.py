# -*- coding: utf-8 -*-
"""
Created on Fri Mar 18 18:27:09 2016

@author: elliott
"""

from cl.corpus_importer.import_columbia.parse_judges import find_judges
from cl.lib.import_lib import find_person
from cl.search.models import OpinionCluster


def assign_authors(testing=False):

    clusters = OpinionCluster.objects.exclude(judges='')

    for cluster in clusters:
        print("Processing: %s" % cluster)
        print("  Judge string: %s" % cluster.judges)

        judges = find_judges(cluster.judges)

        if len(judges) == 0:
            continue

        candidates = []
        for judge in judges:
            candidates.append(find_person(judge,
                                          cluster.docket.court_id,
                                          case_date=cluster.date_filed))
        candidates = [c for c in candidates if c is not None]

        opinion = cluster.sub_opinions.all()[0]

        if len(candidates) == 1:
            opinion.author = candidates[0]
            print '  Author assigned: ', candidates[0]
        elif len(candidates) > 1:
            opinion.panel = candidates
            print '  Panel assigned:', candidates
        else:
            print '  No match.'

        if not testing:
            opinion.save()


