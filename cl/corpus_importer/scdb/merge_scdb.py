"""
Process here will be to iterate over every item in the SCDB and to locate it in
CourtListener.

Location is done by:
 - Looking in the `scdb_id` field. During the first run of this
   program we expect this to fail for all items since they will not have this
   field populated yet. During subsequent runs, this field will have hits and
   will provide improved performance.
 - Looking for matching U.S. and docket number.

Once located, we update items:
 - Case name -- will this automatically fix the docket as well?
 - Citations (Lexis, US, L.Ed., etc.)
 - Docket number?
 - scdb_id
 - votes_majority & votes_minority
 - decision_direction
"""
import sys
sys.path.insert(0, "/var/www/courtlistener")

import csv
import os
from cl.search.models import OpinionCluster
from datetime import date, datetime

DATA_DIR = os.path.dirname(__name__)
SCDB_FILENAME = os.path.join(DATA_DIR, 'data',
                             'SCDB_2015_01_caseCentered_Citation.csv')
SCDB_BEGINS = date(1946, 11, 18)
SCDB_ENDS = date(2014, 6, 19)

DEBUG = True


# Relevant numbers:
#  - 7907: After this point we don't seem to have any citations for items.


def set_if_falsy(obj, attribute, new_value):
    """Check if the value passed in is Falsy. If so, set it to the value of
    new_value.
    """
    current_value = getattr(obj, attribute)
    if current_value is not None:
        current_value = current_value.strip()
    if not current_value:
        setattr(obj, attribute, new_value)
    else:
        # Report if there's a difference -- that might spell trouble.
        if current_value != new_value:
            print ("      WARNING: Didn't set '{attr}' attribute on obj "
                   "{obj_id} because it already had a value, but the new "
                   "value ('{new}') differs from current value "
                   "('{current}').".format(
                attr=attribute,
                obj_id=obj.pk,
                new=new_value,
                old=current_value,
            ))


def enhance_item_with_scdb(cluster, scdb_info):
    """Good news: A single Cluster object was found for the SCDB record.

    Take that item and enhance it with the SCDB content.
    """
    print '    --> Enhancing cluster %s with data from SCDB.' % cluster.pk
    attribute_pairs = [
        ('federal_cite_one', 'usCite'),
        ('federal_cite_two', 'sctCite'),
        ('federal_cite_three', 'ledCite'),
        ('lexis_cite', 'lexisCite'),
        ('scdb_id', 'caseId'),
        ('scdb_votes_majority', 'majVotes'),
        ('scdb_votes_minority', 'minVotes'),
        ('scdb_decision_direction', 'decisionDirection'),
    ]
    for attr, lookup_key in attribute_pairs:
        set_if_falsy(cluster, attr, scdb_info[lookup_key])

    set_if_falsy(cluster.docket, 'docket_number', scdb_info['docket'])

    if not DEBUG:
        cluster.docket.save()
        cluster.save()


def winnow_by_docket_number(clusters, d):
    """Go through each of the clusters and see if they have a matching docket
    number. Return only those ones that do.
    """
    good_cluster_ids = []
    for cluster in clusters:
        dn = cluster.docket.docket_number
        if dn is not None:
            dn = dn.replace(', Original', ' ORIG')
            dn = dn.replace('___, ORIGINAL', 'ORIG')
            dn = dn.replace(', Orig', ' ORIG')
            dn = dn.replace(', Misc', ' M')
            dn = dn.replace(' Misc', ' M')
            dn = dn.replace('NO. ', '')
            if dn == d['docket']:
                good_cluster_ids.append(cluster.pk)

    # Convert our list of IDs back into a QuerySet for consistency.
    return OpinionCluster.objects.filter(pk__in=good_cluster_ids)


def get_human_review(clusters, d):
    for i, cluster in enumerate(clusters):
        print '    %s: Cluster %s:' % (i, cluster.pk)
        print '      https://www.courtlistener.com/opinion/%s/slug/' % cluster.pk
        print '      %s' % cluster.case_name
        print '      %s' % cluster.docket.docket_number
    print '  SCDB info:'
    print '    %s' % d['caseName']
    print '    %s' % d['docket']
    choice = raw_input('  Which item should we update? [0-%s] ' %
                       (len(clusters) - 1))

    try:
        choice = int(choice)
        cluster = clusters[choice]
    except ValueError:
        cluster = None
    return cluster


def iterate_scdb_and_take_actions(
        action_zero,
        action_one,
        action_many,
        start_row=0):
    """Iterates over the SCDB, looking for a single match for every item. If
    a single match is identified it takes the action in the action_one
    function using the Cluster identified and the dict of the SCDB
    information.

    If zero or many results are found it runs the action_zero or action_many
    functions. The action_many function takes the QuerySet of Clusters and
    the dict of SCDB info as parameters and returns the single item in
    the QuerySet that should have action_one performed on it.

    The action_zero function takes only the dict of SCDB information, and uses
    that to construct or identify a Cluster object that should have action_one
    performed on it.

    If action_zero or action_many return None, no action is taken.
    """
    with open(SCDB_FILENAME) as f:
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        reader = csv.DictReader(f, dialect=dialect)
        for i, d in enumerate(reader):
            # Iterate over every item, looking for matches in various ways.
            if i < start_row:
                continue
            print "Row is: %s. ID is: %s" % (i, d['caseId'])

            clusters = OpinionCluster.objects.none()
            if len(clusters) == 0:
                print "  Checking scdb_id for SCDB field 'caseID'...",
                clusters = OpinionCluster.objects.filter(scdb_id=d['caseId'])
                print "%s matches found." % clusters.count()
            if d['usCite'].strip():
                # Only do these lookups if there is in fact a usCite value.
                if clusters.count() == 0:
                    # None found by scdb_id. Try by citation number
                    print "  Checking by federal_cite_one..",
                    clusters = OpinionCluster.objects.filter(
                        federal_cite_one=d['usCite'])
                    print "%s matches found." % clusters.count()
                if clusters.count() == 0:
                    print "  Checking by federal_cite_two...",
                    clusters = OpinionCluster.objects.filter(
                        federal_cite_two=d['usCite'])
                    print "%s matches found." % clusters.count()
                if clusters.count() == 0:
                    print "  Checking by federal_cite_three...",
                    clusters = OpinionCluster.objects.filter(
                        federal_cite_three=d['usCite'])
                    print "%s matches found." % clusters.count()

            # At this point, we need to start getting more experimental b/c
            # the easy ways to find items did not work. Items matched here are
            # ones that lack citations.
            if clusters.count() == 0:
                # try by date and then winnow by docket number
                print "  Checking by date...",
                clusters = OpinionCluster.objects.filter(
                    date_filed=datetime.strptime(
                        d['dateDecision'], '%m/%d/%Y'
                    ),
                    docket__court_id='scotus',
                )
                print "%s matches found." % clusters.count()
                print "    Winnowing by docket number...",
                clusters = winnow_by_docket_number(clusters, d)
                print "%s matches found." % clusters.count()

            # Searching complete, run actions.
            if clusters.count() == 0:
                print '  No items found.'
                cluster = action_zero(d)
            elif clusters.count() == 1:
                print '  Exactly one match found.'
                cluster = clusters[0]
            else:
                print '  %s items found:' % clusters.count()
                cluster = action_many(clusters, d)

            if cluster is not None:
                action_one(cluster, d)
            else:
                print '  OK. No changes will be made.'


def main():
    iterate_scdb_and_take_actions(
        action_zero=lambda *args, **kwargs: None,
        action_one=enhance_item_with_scdb,
        action_many=get_human_review,
    )


if __name__ == '__main__':
    main()
