# coding=utf-8
import logging

import networkx as nx
from celery import group
from django.conf import settings
from django.core.management import BaseCommand, call_command, CommandError
from reporters_db import REPORTERS

from cl.citations.find_citations import Citation
from cl.citations.match_citations import get_years_from_reporter, \
    build_date_range
from cl.citations.tasks import get_document_citations, \
    identify_parallel_citations
from cl.lib.db_tools import queryset_generator
from cl.lib.sunburnt import sunburnt
from cl.search.models import Opinion, OpinionCluster

logger = logging.getLogger(__name__)

# Parallel citations need to be identified this many times before they should be
# added to the database.
EDGE_RELEVANCE_THRESHOLD = 20


def make_edge_list(group):
    """Convert a list of parallel citations into a list of tuples.

    This satisfied networkx.
    """
    out = []
    for i, citation in enumerate(group):
        try:
            t = (citation, group[i + 1])
        except IndexError:
            # End of the list
            break
        else:
            out.append(t)
    return out


class Command(BaseCommand):
    help = ('Parse the entire corpus, identifying parallel citations. Add them '
            'to the database if sufficiently accurate and requested by the '
            'user.')

    def __init__(self, stdout=None, stderr=None, no_color=False):
        super(Command, self).__init__(stdout=None, stderr=None, no_color=False)
        self.g = nx.Graph()
        self.conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
        self.update_count = 0

    def add_arguments(self, parser):
        parser.add_argument(
            '--update_database',
            action='store_true',
            default=False,
            help='Save changes to the database',
        )
        parser.add_argument(
            '--update_solr',
            action='store_true',
            default=False,
            help='Update Solr after updating the database',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            default=False,
            help='Parse citations for all items',
        )
        parser.add_argument(
            '--doc_id',
            type=int,
            nargs='*',
            help='ids of citing opinions',
        )

    def monkey_patch_citation(self):
        Citation.__eq__ = Citation.fuzzy_eq
        Citation.__hash__ = Citation.fuzzy_hash

    def match_on_citation(self, citation):
        """Attempt to identify the item referred to by the citation."""
        main_params = {
            'fq': [
                'status:Precedential',
                'citation:("%s"~5)' % citation.base_citation(),
            ],
            'caller': 'citation.add_parallel_citations',
        }

        if citation.year:
            start_year = end_year = citation.year
        else:
            start_year, end_year = get_years_from_reporter(citation)
        main_params['fq'].append(
            'dateFiled:%s' % build_date_range(start_year, end_year)
        )

        if citation.court:
            main_params['fq'].append('court_exact:%s' % citation.court)

        # Query Solr
        return self.conn.raw_query(**main_params).execute()

    def add_citation_to_cluster(self, citation, cluster):
        """Update a cluster object to have the new value.

        Start by looking up the citation type in the reporters DB, then using
        that value, attempt to put the new citation in the correct field. Only
        add it, however, if there's not already a value!
        """
        cite_type = (REPORTERS[citation.canonical_reporter]
                     [citation.lookup_index]
                     ['cite_type'])
        logger.info("    Citation type is: %s\n" % cite_type)
        cite_attr = None
        if cite_type in ['federal', 'state', 'specialty']:
            for number in ['one', 'two', 'three']:
                cite_attr = '%s_cite_%s' % (cite_type, number)
                if not getattr(cluster, cite_attr):
                    break
        else:
            if cite_type == 'state_regional':
                cite_attr = 'state_cite_regional'
            elif cite_type == 'scotus_early':
                cite_attr = 'scotus_early_cite'
            elif cite_type == 'specialty_lexis':
                cite_attr = 'lexis_cite'
            elif cite_type == 'specialty_west':
                cite_attr = 'westlaw_cite'
            elif cite_type == 'neutral':
                cite_attr = 'neutral_cite'

        has_empty_field = not getattr(cluster, cite_attr)
        if cite_attr is not None and has_empty_field:
            setattr(cluster, cite_attr, citation.base_citation())
            logger.info("    Set %s attribute of cluster %s to %s.\n" % (
                cite_attr,
                cluster.pk,
                citation.base_citation(),
            ))
            self.update_count += 1
        else:
            logger.info("    Unable to find empty space in cluster %s for "
                        "citation %s.\n" % (
                cluster.pk,
                citation.base_citation()
            ))

    def _update_cluster_with_citation(self, cluster, citation):
        """Update the cluster with the citation object."""
        logger.info("  Updating cluster %s with value %s" %
                    (cluster.pk, citation.base_citation()()))

        # Make sure we don't get an item that has the citation already.
        # Just a safety check.
        lookup_fields = OpinionCluster().citation_fields
        problem = False
        for field in lookup_fields:
            if getattr(cluster, field) == citation.base_citation():
                problem = True
                break

        if not problem:
            self.add_citation_to_cluster(
                citation=citation,
                cluster=cluster,
            )

    def handle_subgraph(self, sub_graph, options):
        """Add edges to the database if significant.

        An earlier version of the code simply looked at each edge, but this
        looks at sub_graphs within the main graph. This is different (and
        better) because the main graph might have multiple nodes like so:

            A <-- (22 US 33): This node is in the DB already
            |
            B <-- (2013 LEXIS 223948): This node is not yet in the DB
            |
            C <-- (2013 WL 3808347): This node is not yet in the DB
            |
            D <-- This node can be disregarded because it has low edge weight.

        If we handled this edge by edge, we might process B --> C before doing
        A --> B. If we did that, we'd get zero results for B and C, and we'd
        add nothing. That'd be bad, since there's a strong edge between A, B,
        and C.

        Instead, we process this as a graph, looking at all the nodes at once.
        """
        # Remove nodes that are only connected weakly.
        for node in sub_graph.nodes():
            has_good_edge = False
            for a, b, data in sub_graph.edges([node], data=True):
                if data['weight'] > EDGE_RELEVANCE_THRESHOLD:
                    has_good_edge = True
                    break
            if not has_good_edge:
                sub_graph.remove_node(node)

        if len(sub_graph.nodes()) == 0:
            logger.info("  No strong edges found. Pass.\n")
            return

        # Look up all remaining nodes in Solr, and make a (node, results) pair.
        result_sets = []
        for node in sub_graph.nodes():
            result_sets.append((node, self.match_on_citation(node)))

        if sum(len(results) for node, results in result_sets) == 0:
            logger.info("  Got no results for any citation. Pass.\n")
            return

        if all(len(results) > 0 for node, results in result_sets):
            logger.info("  Got results for all citations. Pass.\n")
            return

        # Remove any node-results pairs with more than than one result.
        result_sets = filter(
            lambda (n, r): len(r) > 1,
            result_sets,
        )

        # For result_sets with more than 0 results, do all the citations have
        # the same ID?
        if len(set([results[0]['cluster_id'] for node, results in
                    result_sets if len(results) > 0])) > 1:
            logger.info("  Got multiple IDs for the citations. Pass.\n")
            return

        # Are the number of unique reporters equal to the number of results?
        if len(set([node.reporter for node, results in
                    result_sets])) != len(result_sets):
            logger.info("  Got duplicated reporter in citations. Pass.\n")
            return

        # Get the cluster. By now we know all results have either 0 or 1 item.
        oc = None
        for node, results in result_sets:
            if len(results) > 0:
                oc = OpinionCluster.objects.get(pk=results[0]['cluster_id'])
                break

        if oc is not None:
            # Update the cluster with all the nodes that had no results.
            for node, results in result_sets:
                if len(results) == 0:
                    # add the citation to the cluster.
                    self._update_cluster_with_citation(oc, node)
            if options['update_database']:
                oc.save()

    def add_groups_to_network(self, citation_groups):
        """Add the citation groups from an opinion to the global network
        object, normalizing the Citation objects.
        """
        for group in citation_groups:
            edge_list = make_edge_list(group)
            for edge in edge_list:
                if any(e for e in edge if e.reporter_found in ['Id.', 'Cr.']):
                    # Alas, Idaho can be abbreviated as Id. This creates lots of
                    # problems, so if made a match on "Id." we simple move on.
                    # Ditto for Cr. (short for Cranch)
                    return

                if self.g.has_edge(*edge):
                    # Increment the weight of the edge.
                    self.g[edge[0]][edge[1]]['weight'] += 1
                else:
                    self.g.add_edge(*edge, weight=1)

    @staticmethod
    def do_solr(options):
        """Update Solr if requested, or report if not."""
        if options['update_solr']:
            call_command(
                'cl_update_index',
                '--type', 'opinions',
                '--solr-url', settings.SOLR_OPINION_URL,
                '--noinput',
                '--update',
                '--everything',
                '--do-commit',
            )
        else:
            logger.info("\nSolr index not updated. You may want to do so "
                        "manually.\n")

    def handle(self, *args, **options):
        """Identify parallel citations and save them as requested.

        This process proceeds in two phases. The first phase is to work through
        the entire corpus, identifying citations that occur very near to each
        other. These are considered parallel citations, and they are built into
        a graph data structure where citations are nodes and each parallel
        citation is an edge. The weight of each edge is determined by the
        number of times a parallel citation has been identified between two
        citations. This should solve problems like typos or other issues with
        our heuristic approach.

        The second phase of this process is to update the database with the
        high quality citations. This can only be done by matching the citations
        with actual items in the database and then updating them with parallel
        citations that are sufficiently likely to be good.
        """
        no_option = (not any([options.get('doc_id'), options.get('all')]))
        if no_option:
            raise CommandError("Please specify if you want all items or a "
                               "specific item.")
        if not options['update_database']:
            logger.info(
                "--update_database is not set. No changes will be made to the "
                "database."
            )

        # Update Citation object to consider similar objects equal.
        self.monkey_patch_citation()

        logger.info("## Entering phase one: Building a network object of "
                    "all citations.\n")
        q = Opinion.objects.all()
        if options.get('doc_id'):
            q = q.filter(pk__in=options['doc_id'])
        count = q.count()
        opinions = queryset_generator(q, chunksize=10000)

        node_count = edge_count = completed = 0
        subtasks = []
        for o in opinions:
            subtasks.append(
                # This will call the second function with the results from the
                # first.
                get_document_citations.s(o) | identify_parallel_citations.s()
            )
            last_item = (count == completed + 1)
            if (completed % 50 == 0) or last_item:
                job = group(subtasks)
                result = job.apply_async().join()
                [self.add_groups_to_network(citation_groups) for
                 citation_groups in result]
                subtasks = []

            completed += 1
            if completed % 250 == 0 or last_item:
                # Only do this once in a while.
                node_count = len(self.g.nodes())
                edge_count = len(self.g.edges())
            self.stdout.write("\r  Completed %s of %s. (%s nodes, %s edges)" % (
                completed,
                count,
                node_count,
                edge_count,
            ))
            self.stdout.flush()

        logger.info("\n\n## Entering phase two: Saving the best edges to "
                    "the database.\n\n")
        for sub_graph in nx.connected_component_subgraphs(self.g):
            self.handle_subgraph(sub_graph, options)

        logger.info("\n\n## Done. Added %s new citations." % self.update_count)

        self.do_solr(options)
