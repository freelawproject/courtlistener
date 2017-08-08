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
import string
from datetime import datetime

from django.core.management import CommandError
from django.db.models import Q

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_diff import gen_diff_ratio
from cl.search.models import OpinionCluster


# Relevant numbers:
#  - 7907: After this point we don't seem to have any citations for items.


class Command(VerboseCommand):
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
        super(Command, self).handle(*args, **options)
        self.debug = options['debug']
        self.file = options['file']
        self.skip_human_review = options['skip_human_review']
        if self.skip_human_review and not self.debug:
            raise CommandError('Cannot skip review without --debug flag.')
        if self.skip_human_review:
            self.skipped_count = 0

        self.iterate_scdb_and_take_actions(
            action_zero=lambda *args, **kwargs: None,
            action_one=self.enhance_item_with_scdb,
            action_many=self.get_human_review,
            start_row=options['start_at'],
        )

        if self.skip_human_review:
            logger.info("\nSkipped %s items in SCDB which came up for human "
                        "review." % self.skipped_count)

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
        error = False
        if all([does_not_currently_have_a_value, current_value_not_zero,
                new_value_not_blank]):
            logger.info("      Updating %s with %s." %
                        (attribute, new_value.encode('utf-8')))
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
                logger.warn(
                    "WARNING: Didn't set '{attr}' attribute on obj {obj_id} "
                    "because it already had a value, but the new value "
                    "('{new}') differs from current value ('{current}')".format(
                        attr=attribute,
                        obj_id=obj.pk,
                        new=new_value,
                        current=current_value.encode('utf-8'),
                    )
                )
                error = True
            else:
                # The values were the same.
                logger.info("'%s' field unchanged -- old and new values were "  
                            "the same: %s" % (attribute, new_value))
        return error

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
        error = False
        for field in ['federal_cite_one', 'federal_cite_two',
                      'federal_cite_three']:
            # Update the value in place (ie, replace the U.S. citation with a
            # U.S. citation. Identify available fields.
            value = getattr(cluster, field).strip()
            if not value:
                available_fields.append(field)
                continue

            if "U.S." in value:
                error = self.set_if_falsy(cluster, field, scdb_info['usCite'])
                us_done = True
            elif "S. Ct." in value:
                error = self.set_if_falsy(cluster, field, scdb_info['sctCite'])
                sct_done = True
            elif "L. Ed." in value:
                error = self.set_if_falsy(cluster, field, scdb_info['ledCite'])
                led_done = True
            else:
                logger.warn("      WARNING: Fell through search for citation.")
                save = False
        if error:
            save = False

        num_undone_fields = sum([f for f in [us_done, sct_done, led_done] if
                                 f is False])
        if num_undone_fields > len(available_fields):
            logger.warn("WARNING: More values were found than there were "   
                        "slots to put them in. Time to create "
                        "federal_cite_four?")
            save = False
        else:
            # Save undone values into available fields. Any value that wasn't
            # updated above gets slotted into the fields that remain.
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
        logger.info('Enhancing cluster {id} with data from SCDB ('
                    'https://www.courtlistener.com{path}).'.format(
            id=cluster.pk,
            path=cluster.get_absolute_url(),
        ))
        attribute_pairs = [
            ('scdb_votes_majority', 'majVotes'),
            ('scdb_votes_minority', 'minVotes'),
            ('scdb_decision_direction', 'decisionDirection'),
        ]
        for attr, lookup_key in attribute_pairs:
            self.set_if_falsy(cluster, attr, scdb_info[lookup_key])

        self.set_if_falsy(cluster.docket, 'docket_number', scdb_info['docket'])
        federal_ok = self.do_federal_citations(cluster, scdb_info)
        scdb_ok = self.set_if_falsy(cluster, 'scdb_id', 'caseId')
        lexis_ok = self.set_if_falsy(cluster, 'lexis_cite', 'lexisCite')

        if all([federal_ok, scdb_ok, lexis_ok]):
            logger.info("      Saving to database (or faking if debug=True)")
            if not self.debug:
                cluster.docket.save()
                cluster.save()
        else:
            logger.info("      Item not saved due to collision or error. "
                        "Please edit by hand.")

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

    @staticmethod
    def winnow_by_case_name(clusters, d):
        """
        Go through the clusters that are matched and see if one matches by
        case name.

        :param clusters: A QuerySet object of clusters.
        :param d: The matching SCDB data
        :return: A QuerySet object of clusters, hopefully winnowed to a single
        result.
        """
        good_cluster_ids = []
        bad_words = ['v', 'versus']
        exclude = set(string.punctuation)
        scdb_case_name = ''.join(c for c in d['caseName'] if
                                 c not in exclude)
        scdb_words = set(scdb_case_name.lower().split())
        for cluster in clusters:
            case_name = ''.join(c for c in cluster.case_name if
                                c not in exclude)
            case_name_words = case_name.lower().split()
            cluster_words = set([word for word in case_name_words if
                                 word not in bad_words])
            if scdb_words.issuperset(cluster_words):
                good_cluster_ids.append(cluster.pk)

        if len(good_cluster_ids) == 1:
            return OpinionCluster.objects.filter(pk__in=good_cluster_ids)
        else:
            # Alas: No progress made.
            return clusters

    def get_human_review(self, clusters, d):
        for i, cluster in enumerate(clusters):
            logger.info('%s: Cluster %s (%0.3f sim):' % (
                i,
                cluster.pk,
                gen_diff_ratio(
                    cluster.case_name.lower(),
                    d['caseName'].lower()
                ),
            ))
            logger.info('https://www.courtlistener.com%s' %
                        cluster.get_absolute_url())
            logger.info('      %s' % cluster.case_name.encode('utf-8'))
            if cluster.docket.docket_number:
                logger.info(cluster.docket.docket_number.encode('utf-8'))
            logger.info(cluster.date_filed)
        logger.info('SCDB info:')
        logger.info(d['caseName'])
        if d['docket']:
            logger.info(d['docket'])
        logger.info(d['dateDecision'])

        if self.skip_human_review:
            logger.info('Skipping human review and just returning the first '
                        'item.')
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
                logger.info("\nRow is: %s. ID is: %s (%s)" % (i, d['caseId'],
                                                              d['caseName']))

                clusters = OpinionCluster.objects.none()
                if len(clusters) == 0:
                    logger.info("Checking scdb_id for SCDB field 'caseID'...")
                    clusters = (OpinionCluster.objects
                                .filter(scdb_id=d['caseId']))
                    logger.info("%s matches found." % clusters.count())
                if d['usCite'].strip():
                    # Only do these lookups if there is in fact a usCite value.
                    # Newer additions don't yet have citations.
                    if clusters.count() == 0:
                        # None found by scdb_id. Try by citation number
                        logger.info("  Checking by federal_cite_one, _two, or "
                                    "_three...")
                        clusters = OpinionCluster.objects.filter(
                            Q(federal_cite_one=d['usCite']) |
                            Q(federal_cite_two=d['usCite']) |
                            Q(federal_cite_three=d['usCite']),
                            scdb_id='',
                        )
                        logger.info("%s matches found." % clusters.count())

                # At this point, we need to start getting more experimental b/c
                # the easy ways to find items did not work. Items matched here
                # are ones that lack citations.
                if clusters.count() == 0:
                    # try by date and then winnow by docket number
                    logger.info("  Checking by date...")
                    clusters = OpinionCluster.objects.filter(
                        date_filed=datetime.strptime(
                            d['dateDecision'], '%m/%d/%Y'
                        ),
                        docket__court_id='scotus',
                        scdb_id='',
                    )
                    logger.info("%s matches found." % clusters.count())

                if clusters.count() > 1:
                    if d['docket']:
                        logger.info("Winnowing by docket number...")
                        clusters = self.winnow_by_docket_number(clusters, d)
                        logger.info("%s matches found." % clusters.count())
                    else:
                        logger.info("Cannot winnow by docket number -- there "
                                    "isn't one.")

                if clusters.count() > 1:
                    logger.info("Winnowing by case name...")
                    clusters = self.winnow_by_case_name(clusters, d)
                    logger.info("%s matches found." % clusters.count())

                # Searching complete, run actions.
                if clusters.count() == 0:
                    logger.info('No items found.')
                    cluster = action_zero(d)
                elif clusters.count() == 1:
                    logger.info('Exactly one match found.')
                    cluster = clusters[0]
                else:
                    logger.info('%s items found:' % clusters.count())
                    cluster = action_many(clusters, d)

                if cluster is not None:
                    action_one(cluster, d)
                else:
                    logger.info('OK. No changes will be made.')

