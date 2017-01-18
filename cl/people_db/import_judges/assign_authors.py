# -*- coding: utf-8 -*-
"""
Created on Fri Mar 18 18:27:09 2016

@author: elliott
"""

from unidecode import unidecode

from cl.audio.models import Audio
from cl.lib.import_lib import get_candidate_judge_objects
from cl.search.models import OpinionCluster


def assign_authors_to_opinions(jurisdictions=None, testing=False):
    clusters = (OpinionCluster.objects
                .exclude(judges='')
                .select_related('docket__court__id')
                .only('date_filed', 'judges', 'docket__court_id'))
    if jurisdictions is not None:
        clusters = clusters.filter(
            docket__court__jurisdiction__in=jurisdictions)
    total = clusters.count()
    i = 0

    for cluster in clusters:
        i += 1
        print u"(%s/%s): Processing: %s, %s" % (i, total, cluster.pk,
                                                cluster.date_filed)

        judge_str = unidecode(cluster.judges)
        print "  Judge string: %s" % judge_str

        if 'curiam' in judge_str.lower():
            opinion = cluster.sub_opinions.all()[0]
            opinion.per_curiam = True
            print u'  Per Curiam assigned.'
            if not testing:
                opinion.save(index=False)
            continue

        candidates = get_candidate_judge_objects(judge_str,
                                                 cluster.docket.court_id,
                                                 cluster.date_filed)
        if len(candidates) < 1:
            # No DB matches
            print u'  No match.'

        elif len(candidates) == 1:
            # only one candidate, assign author
            opinion = cluster.sub_opinions.all()[0]
            opinion.author = candidates[0]
            print u'  Author assigned: %s' % unidecode(str(candidates[0]))
            if not testing:
                opinion.save(index=False)

        elif len(candidates) > 1:
            # more than one DB match, assign panel
            print u'  Panel assigned: %s' % candidates
            if not testing:
                for candidate in candidates:
                    cluster.panel.add(candidate)


def assign_authors_to_oral_arguments(testing=False):
    afs = (Audio.objects.exclude(judges='')
           .select_related('docket__court_id', 'docket__date_argued')
           .only('docket__date_argued', 'judges', 'docket__court_id'))
    for af in afs:
        judge_str = unidecode(af.judges)
        print "  Judge string: %s" % judge_str

        candidates = get_candidate_judge_objects(judge_str, af.docket.court_id,
                                                 af.docket.date_argued)
        for candidate in candidates:
            if not testing:
                af.panel.add(candidate)
