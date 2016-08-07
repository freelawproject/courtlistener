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
 - Citations (Lexis, US, L.Ed., etc.)
 - Docket number
 - scdb_id
 - votes_majority & votes_minority
 - decision_direction
"""
import csv

from django.core.management import BaseCommand
from django.core.management import CommandError
from django.db.models import Q

from cl.search.models import OpinionCluster
from datetime import date, datetime

# Relevant numbers:
#  - 7907: After this point we don't seem to have any citations for items.


class Command(BaseCommand):
    help = 'Import data from the SCDB Case Centered CSV.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            default=False,
            help="Don't change the data. Only pretend."
        )
        parser.add_argument(
            '--start_at',
            type=int,
            default=0,
            help="The row number you wish to begin at in the SCDB CSV"
        )
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help="The path to the SCDB Case Centered file you wish to input."
        )
        parser.add_argument(
            '--skip-human-review',
            action='store_true',
            default=False,
            help="Don't seek human review. Instead report the number of cases "
                 "needing human review at the end."
        )

    def handle(self, *args, **options):
        self.debug = options['debug']
        self.file = options['file']
        self.skip_human_review = options['skip_human_review']
        if self.skip_human_review and not self.debug:
            raise CommandError(u'Cannot skip review without --debug flag.')
        if self.skip_human_review:
            self.skipped_count = 0

        self.iterate_scdb_and_take_actions(
            action_zero=lambda *args, **kwargs: None,
            action_one=self.enhance_item_with_scdb,
            action_many=self.get_human_review,
            start_row=options['start_at'],
        )

        if self.skip_human_review:
            print(u"\nSkipped %s items in SCDB which came up for human review." %
                  self.skipped_count)

    @staticmethod
    def set_if_falsy(obj, attribute, new_value):
        """Check if the value passed in is Falsy. If so, set it to the value of
        new_value.
        """
        current_value = getattr(obj, attribute)
        if current_value is not None and isinstance(current_value, basestring):
            current_value = current_value.strip()

        does_not_currently_have_a_value = not current_value
        current_value_not_zero = current_value != 0
        new_value_not_blank = new_value.strip() != ''
        if all([does_not_currently_have_a_value, current_value_not_zero,
                new_value_not_blank]):
            print(u"      Updating %s with %s." % (attribute, new_value))
            setattr(obj, attribute, new_value)
        else:
            # Report if there's a difference -- that might spell trouble.
            values_differ = False
            if (isinstance(current_value, basestring) and
                    isinstance(new_value, basestring) and
                    ''.join(current_value.split()) != ''.join(new_value.split())):
                # Handles strings and normalizes them for comparison.
                values_differ = True
            elif (isinstance(current_value, int) and
                  current_value != int(new_value)):
                # Handles ints, which need no normalization for comparison.
                values_differ = True

            if values_differ:
                print (u"      WARNING: Didn't set '{attr}' attribute on obj "
                       u"{obj_id} because it already had a value, but the new "
                       u"value ('{new}') differs from current value "
                       u"('{current}').".format(
                        attr=attribute,
                        obj_id=obj.pk,
                        new=new_value,
                        current=current_value,
                ))
            else:
                # The values were the same.
                print u"      '%s' field unchanged -- old and new values were " \
                      u"the same." % attribute

    def do_federal_citations(self, cluster, scdb_info):
        """
        Handle the federal_cite fields differently, since they may have the
        values in any order.

        :param cluster: The Cluster to be changed.
        :param scdb_info: A dict with the SCDB information.
        :return: save: A boolean indicating whether the item should be saved.
        """
        save = True
        us_done, sct_done, led_done = False, False, False
        available_fields = []
        for field in ['federal_cite_one', 'federal_cite_two',
                      'federal_cite_three']:
            value = getattr(cluster, field).strip()
            if not value:
                available_fields.append(field)
                continue

            if "U.S." in value:
                self.set_if_falsy(cluster, field, scdb_info['usCite'])
                us_done = True
            elif "S. Ct." in value:
                self.set_if_falsy(cluster, field, scdb_info['sctCite'])
                sct_done = True
            elif "L. Ed." in value:
                self.set_if_falsy(cluster, field, scdb_info['ledCite'])
                led_done = True
            else:
                print(u"      WARNING: Fell through search for citation.")
                save = False

        num_undone_fields = sum([f for f in [us_done, sct_done, led_done] if
                                 f is False])
        if num_undone_fields > len(available_fields):
            print u"       WARNING: More values were found than there were " \
                  u"slots to put them in. Time to create federal_cite_four?"
            save = False
        else:
            # Save undone values into available fields.
            for field in available_fields:
                if not us_done:
                    us_done = True
                    if scdb_info['usCite']:
                        self.set_if_falsy(cluster, field, scdb_info['usCite'])
                        # Continue if the value got set. Otherwise, fall let
                        # the next value fill the available field.
                        continue
                if not sct_done:
                    sct_done = True
                    if scdb_info['sctCite']:
                        self.set_if_falsy(cluster, field, scdb_info['sctCite'])
                        continue
                if not led_done:
                    led_done = True
                    if scdb_info['ledCite']:
                        self.set_if_falsy(cluster, field, scdb_info['ledCite'])
                        continue

        return save

    def enhance_item_with_scdb(self, cluster, scdb_info):
        """Good news: A single Cluster object was found for the SCDB record.

        Take that item and enhance it with the SCDB content.
        """
        print (u'    --> Enhancing cluster {id} with data from SCDB ('
               u'https://www.courtlistener.com{path}).'.format(
                id=cluster.pk,
                path=cluster.get_absolute_url(),
        ))
        attribute_pairs = [
            ('lexis_cite', 'lexisCite'),
            ('scdb_id', 'caseId'),
            ('scdb_votes_majority', 'majVotes'),
            ('scdb_votes_minority', 'minVotes'),
            ('scdb_decision_direction', 'decisionDirection'),
        ]
        for attr, lookup_key in attribute_pairs:
            self.set_if_falsy(cluster, attr, scdb_info[lookup_key])

        self.set_if_falsy(cluster.docket, 'docket_number', scdb_info['docket'])
        save = self.do_federal_citations(cluster, scdb_info)

        if save:
            print(u"      Saving to database (or faking if debug=True)")
            if not self.debug:
                cluster.docket.save()
                cluster.save()
        else:
            print(u"      Item not saved due to collision or error. Please "
                  u"edit by hand.")

    @staticmethod
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

    def get_human_review(self, clusters, d):
        for i, cluster in enumerate(clusters):
            print u'    %s: Cluster %s:' % (i, cluster.pk)
            print u'      https://www.courtlistener.com%s' % cluster.get_absolute_url()
            print u'      %s' % cluster.case_name
            print u'      %s' % cluster.docket.docket_number
        print u'  SCDB info:'
        print u'    %s' % d['caseName']
        print u'    %s' % d['docket']

        if self.skip_human_review:
            print(u'  Skipping human review and just returning the first item.')
            self.skipped_count += 1
            return clusters[0]
        else:
            choice = raw_input('  Which item should we update? [0-%s] ' %
                               (len(clusters) - 1))

            try:
                choice = int(choice)
                cluster = clusters[choice]
            except ValueError:
                cluster = None
            return cluster

    def iterate_scdb_and_take_actions(
            self,
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

        The action_zero function takes only the dict of SCDB information, and
        uses that to construct or identify a Cluster object that should have
        action_one performed on it.

        If action_zero or action_many return None, no action is taken.
        """
        with open(self.file) as f:
            dialect = csv.Sniffer().sniff(f.read(1024))
            f.seek(0)
            reader = csv.DictReader(f, dialect=dialect)
            for i, d in enumerate(reader):
                # Iterate over every item, looking for matches in various ways.
                if i < start_row:
                    continue
                print u"\nRow is: %s. ID is: %s" % (i, d['caseId'])

                clusters = OpinionCluster.objects.none()
                if len(clusters) == 0:
                    print u"  Checking scdb_id for SCDB field 'caseID'...",
                    clusters = (OpinionCluster.objects
                                .filter(scdb_id=d['caseId']))
                    print u"%s matches found." % clusters.count()
                if d['usCite'].strip():
                    # Only do these lookups if there is in fact a usCite value.
                    # Newer additions don't yet have citations.
                    if clusters.count() == 0:
                        # None found by scdb_id. Try by citation number
                        print u"  Checking by federal_cite_one, _two, or " \
                              u"_three...",
                        clusters = OpinionCluster.objects.filter(
                            Q(federal_cite_one=d['usCite']) |
                            Q(federal_cite_two=d['usCite']) |
                            Q(federal_cite_three=d['usCite']),
                            scdb_id='',
                        )
                        print u"%s matches found." % clusters.count()

                # At this point, we need to start getting more experimental b/c
                # the easy ways to find items did not work. Items matched here
                # are ones that lack citations.
                if clusters.count() == 0:
                    # try by date and then winnow by docket number
                    print u"  Checking by date...",
                    clusters = OpinionCluster.objects.filter(
                        date_filed=datetime.strptime(
                            d['dateDecision'], '%m/%d/%Y'
                        ),
                        docket__court_id='scotus',
                        scdb_id='',
                    )
                    print u"%s matches found." % clusters.count()
                    print u"    Winnowing by docket number...",
                    clusters = self.winnow_by_docket_number(clusters, d)
                    print u"%s matches found." % clusters.count()

                # Searching complete, run actions.
                if clusters.count() == 0:
                    print u'  No items found.'
                    cluster = action_zero(d)
                elif clusters.count() == 1:
                    print u'  Exactly one match found.'
                    cluster = clusters[0]
                else:
                    print u'  %s items found:' % clusters.count()
                    cluster = action_many(clusters, d)

                if cluster is not None:
                    action_one(cluster, d)
                else:
                    print u'  OK. No changes will be made.'

