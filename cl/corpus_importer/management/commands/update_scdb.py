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
from django.db import IntegrityError
from django.utils.encoding import force_bytes
from eyecite.find import get_citations

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_diff import gen_diff_ratio
from cl.search.models import Citation, OpinionCluster

# Relevant numbers:
#  - 7907: After this point we don't seem to have any citations for items.


class Command(VerboseCommand):
    help = "Import data from the SCDB Case Centered CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Don't change the data. Only pretend.",
        )
        parser.add_argument(
            "--start_at",
            type=int,
            default=0,
            help="The row number you wish to begin at in the SCDB CSV",
        )
        parser.add_argument(
            "--file",
            type=str,
            required=True,
            help="The path to the SCDB Case Centered file you wish to input.",
        )
        parser.add_argument(
            "--skip-human-review",
            action="store_true",
            default=False,
            help="Don't seek human review. Instead report the number of cases "
            "needing human review at the end.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.debug = options["debug"]
        self.file = options["file"]
        self.skip_human_review = options["skip_human_review"]
        if self.skip_human_review and not self.debug:
            raise CommandError("Cannot skip review without --debug flag.")
        if self.skip_human_review:
            self.skipped_count = 0

        self.iterate_scdb_and_take_actions(
            action_zero=lambda *args, **kwargs: None,
            action_one=self.enhance_item_with_scdb,
            action_many=self.get_human_review,
            start_row=options["start_at"],
        )

        if self.skip_human_review:
            logger.info(
                "\nSkipped %s items in SCDB which came up for human "
                "review." % self.skipped_count
            )

    @staticmethod
    def set_if_falsy(obj, attribute, new_value):
        """Check if the value passed in is Falsy. If so, set it to the value of
        new_value.

        return ok: Whether the item was set successfully
        """
        current_value = getattr(obj, attribute)
        if current_value is not None and isinstance(current_value, str):
            current_value = current_value.strip()

        does_not_currently_have_a_value = not current_value
        current_value_not_zero = current_value != 0
        new_value_not_blank = new_value.strip() != ""
        ok = True
        if all(
            [
                does_not_currently_have_a_value,
                current_value_not_zero,
                new_value_not_blank,
            ]
        ):
            logger.info(f"Updating {attribute} with {new_value.encode()}.")
            setattr(obj, attribute, new_value)
        else:
            # Report if there's a difference -- that might spell trouble.
            values_differ = False
            if (
                isinstance(current_value, str)
                and isinstance(new_value, str)
                and "".join(current_value.split())
                != "".join(new_value.split())
            ):
                # Handles strings and normalizes them for comparison.
                values_differ = True
            elif isinstance(current_value, int) and current_value != int(
                new_value
            ):
                # Handles ints, which need no normalization for comparison.
                values_differ = True

            if values_differ:
                logger.warning(
                    "WARNING: Didn't set '{attr}' attribute on obj {obj_id} "
                    "because it already had a value, but the new value "
                    "('{new}') differs from current value ('{current}')".format(
                        attr=attribute,
                        obj_id=obj.pk,
                        new=new_value,
                        current=force_bytes(current_value),
                    )
                )
                ok = False
            else:
                # The values were the same.
                logger.info(
                    "'%s' field unchanged -- old and new values were "
                    "the same: %s" % (attribute, new_value)
                )
        return ok

    @staticmethod
    def do_citations(cluster, scdb_info):
        """
        Handle the citation fields.

        :param cluster: The Cluster to be changed.
        :param scdb_info: A dict with the SCDB information.
        """
        fields = {
            "usCite": ("U.S.", Citation.FEDERAL),
            "sctCite": ("S. Ct.", Citation.FEDERAL),
            "ledCite": ("L. Ed.", Citation.FEDERAL),
            "lexisCite": ("U.S. LEXIS", Citation.LEXIS),
        }
        for scdb_field, reporter_info in fields.items():
            if not scdb_info[scdb_field]:
                continue
            try:
                citation_obj = get_citations(
                    scdb_info[scdb_field],
                    remove_ambiguous=False,
                )[0]
            except IndexError:
                logger.warning(
                    "Unable to parse citation for: %s", scdb_info[scdb_field]
                )
            else:
                cites = cluster.citations.filter(reporter=reporter_info[0])
                if cites.count() == 1:
                    # Update the existing citation.
                    cite = cites[0]
                    cite.volume = citation_obj.groups["volume"]
                    cite.reporter = citation_obj.corrected_reporter()
                    cite.page = citation_obj.groups["page"]
                    cite.save()
                else:
                    try:
                        # Create a new citation
                        Citation.objects.create(
                            cluster=cluster,
                            volume=citation_obj.groups["volume"],
                            reporter=citation_obj.corrected_reporter(),
                            page=citation_obj.groups["page"],
                            type=reporter_info[1],
                        )
                    except IntegrityError:
                        # Violated unique_together constraint. Fine.
                        pass

    def enhance_item_with_scdb(self, cluster, scdb_info):
        """Good news: A single Cluster object was found for the SCDB record.

        Take that item and enhance it with the SCDB content.
        """
        logger.info(
            "Enhancing cluster {id} with data from SCDB ("
            "https://www.courtlistener.com{path}).".format(
                id=cluster.pk, path=cluster.get_absolute_url()
            )
        )
        attribute_tuples = [
            (cluster, "scdb_votes_majority", scdb_info["majVotes"]),
            (cluster, "scdb_votes_minority", scdb_info["minVotes"]),
            (
                cluster,
                "scdb_decision_direction",
                scdb_info["decisionDirection"],
            ),
            (cluster.docket, "docket_number", scdb_info["docket"]),
        ]
        for attribute_tuple in attribute_tuples:
            self.set_if_falsy(*attribute_tuple)

        self.do_citations(cluster, scdb_info)
        scdb_ok = self.set_if_falsy(cluster, "scdb_id", scdb_info["caseId"])

        if scdb_ok:
            logger.info("Saving to database (or faking if debug=True)")
            if not self.debug:
                cluster.docket.save()
                cluster.save()
        else:
            logger.info(
                "Item not saved due to collision or error. Please edit by "
                "hand: scdb_ok: {scdb}".format(scdb=scdb_ok)
            )

    @staticmethod
    def winnow_by_docket_number(clusters, d):
        """Go through each of the clusters and see if they have a matching docket
        number. Return only those ones that do.
        """
        good_cluster_ids = []
        for cluster in clusters:
            dn = cluster.docket.docket_number
            if dn:
                dn = dn.replace(", Original", " ORIG")
                dn = dn.replace("___, ORIGINAL", "ORIG")
                dn = dn.replace(", Orig", " ORIG")
                dn = dn.replace(", Misc", " M")
                dn = dn.replace(" Misc", " M")
                dn = dn.replace("NO. ", "")
                if dn == d["docket"]:
                    good_cluster_ids.append(cluster.pk)
            else:
                # No docket number. Assume it's good for now; it'll get
                # winnowed in the next round.
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
        bad_words = ["v", "versus"]
        exclude = set(string.punctuation)
        scdb_case_name = "".join(c for c in d["caseName"] if c not in exclude)
        scdb_words = set(scdb_case_name.lower().split())
        for cluster in clusters:
            case_name = "".join(
                c for c in cluster.case_name if c not in exclude
            )
            case_name_words = case_name.lower().split()
            cluster_words = {
                word for word in case_name_words if word not in bad_words
            }
            if scdb_words.issuperset(cluster_words):
                good_cluster_ids.append(cluster.pk)

        if len(good_cluster_ids) == 1:
            return OpinionCluster.objects.filter(pk__in=good_cluster_ids)
        else:
            # Alas: No progress made.
            return clusters

    def get_human_review(self, clusters, d):
        for i, cluster in enumerate(clusters):
            logger.info(
                "%s: Cluster %s (%0.3f sim):"
                % (
                    i,
                    cluster.pk,
                    gen_diff_ratio(
                        cluster.case_name.lower(), d["caseName"].lower()
                    ),
                )
            )
            logger.info(
                f"https://www.courtlistener.com{cluster.get_absolute_url()}"
            )
            logger.info(f"{cluster.case_name.encode()}")
            if cluster.docket.docket_number:
                logger.info(cluster.docket.docket_number.encode())
            logger.info(cluster.date_filed)
        logger.info("SCDB info:")
        logger.info(d["caseName"])
        if d["docket"]:
            logger.info(d["docket"])
        logger.info(d["dateDecision"])

        if self.skip_human_review:
            logger.info(
                "Skipping human review and just returning the first item."
            )
            self.skipped_count += 1
            return clusters[0]
        else:
            choice = input(
                f"Which item should we update? [0-{len(clusters) - 1}] "
            )

            try:
                choice = int(choice)
                cluster = clusters[choice]
            except ValueError:
                cluster = None
            return cluster

    def iterate_scdb_and_take_actions(
        self, action_zero, action_one, action_many, start_row=0
    ):
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
        f = open(self.file)
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        reader = csv.DictReader(f, dialect=dialect)
        for i, d in enumerate(reader):
            # Iterate over every item, looking for matches in various ways.
            if i < start_row:
                continue
            logger.info(
                "\nRow is: %s. ID is: %s (%s)", i, d["caseId"], d["caseName"]
            )

            clusters = OpinionCluster.objects.none()
            cluster_count = clusters.count()
            if cluster_count == 0:
                logger.info("Checking scdb_id for SCDB field 'caseID'...")
                clusters = OpinionCluster.objects.filter(scdb_id=d["caseId"])
                cluster_count = clusters.count()
                logger.info("%s matches found.", cluster_count)
            if d["usCite"].strip() and cluster_count == 0:
                # None found by scdb_id. Try by citation number. Only do these
                # lookups if there is a usCite value, as newer cases don't yet
                # have citations.
                logger.info("Checking by federal citation")
                clusters = OpinionCluster.objects.filter(
                    citation=d["usCite"], scdb_id=""
                )
                cluster_count = clusters.count()
                logger.info("%s matches found.", cluster_count)

            # At this point, we need to start getting more experimental b/c
            # the easy ways to find items did not work. Items matched here
            # are ones that lack citations.
            if cluster_count == 0:
                # try by date and then winnow by docket number
                logger.info("Checking by date...")
                clusters = OpinionCluster.objects.filter(
                    date_filed=datetime.strptime(
                        d["dateDecision"], "%m/%d/%Y"
                    ),
                    docket__court_id="scotus",
                    scdb_id="",
                )
                cluster_count = clusters.count()
                if cluster_count == 1:
                    # Winnow these by name too. Date isn't enough.
                    clusters = self.winnow_by_case_name(clusters, d)
                    cluster_count = clusters.count()
                logger.info("%s matches found.", cluster_count)

            if cluster_count > 1:
                if d["docket"]:
                    logger.info("Winnowing by docket number...")
                    clusters = self.winnow_by_docket_number(clusters, d)
                    cluster_count = clusters.count()
                    logger.info("%s matches found.", cluster_count)
                else:
                    logger.info(
                        "Cannot winnow by docket number -- there isn't one."
                    )

            if cluster_count > 1:
                logger.info("Winnowing by case name...")
                clusters = self.winnow_by_case_name(clusters, d)
                cluster_count = clusters.count()
                logger.info("%s matches found.", cluster_count)

            # Searching complete, run actions.
            if cluster_count == 0:
                logger.info("No items found.")
                cluster = action_zero(d)
            elif cluster_count == 1:
                logger.info("Exactly one match found.")
                cluster = clusters[0]
            else:
                logger.info("%s items found:", cluster_count)
                cluster = action_many(clusters, d)

            if cluster is not None:
                action_one(cluster, d)
            else:
                logger.info("OK. No changes will be made.")

        f.close()
