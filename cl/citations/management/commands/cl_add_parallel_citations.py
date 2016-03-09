# coding=utf-8
import pprint
import sys

import networkx as nx
from django.conf import settings
from django.core.management import BaseCommand, call_command, CommandError
from reporters_db import REPORTERS

from cl.citations.match_citations import get_years_from_reporter, \
    build_date_range
from cl.citations.tasks import get_document_citations
from cl.lib.db_tools import queryset_generator
from cl.lib.sunburnt import sunburnt
from cl.search.models import Opinion, OpinionCluster

# This is the distance two reporter abbreviations can be from each other if they
# are considered parallel reporters. For example, "22 U.S. 44, 46 (13 Atl. 33)"
# would have a distance of 4.
PARALLEL_DISTANCE = 5

# Parallel citations need to be identified this many times before they should be
# added to the database.
EDGE_RELEVANCE_THRESHOLD = 5


def identify_parallel_citations(citations):
    """Work through a list of citations and identify ones that are physically
    near each other in the document.

    Return a list of tuples. Each tuple represents a series of parallel
    citations. These will usually be length two, but not necessarily.
    """
    if len(citations) == 0:
        return citations
    citation_indexes = [c.reporter_index for c in citations]
    parallel_citation = [citations[0]]
    parallel_citations = []
    for i, reporter_index in enumerate(citation_indexes[:-1]):
        if reporter_index + PARALLEL_DISTANCE > citation_indexes[i + 1]:
            # The present item is within a reasonable distance from the next
            # item. It's a parallel citation.
            parallel_citation.append(citations[i + 1])
        else:
            # Not close enough. Append what we've got and start a new list.
            if len(parallel_citation) > 1:
                parallel_citations.append(parallel_citation)
            parallel_citation = [citations[i + 1]]

    # In case the last item had a citation.
    if len(parallel_citation) > 1:
        parallel_citations.append(parallel_citation)
    return parallel_citations


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
            start_year, end_year = citation.year
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
        if cite_type in ['federal', 'state', 'specialty']:
            # Try adding it up to three times.
            for number in ['one', 'two', 'three']:
                cite_attr = '%s_cite_%s' % (cite_type, number)
                if not getattr(cluster, cite_attr):
                    setattr(cluster, cite_attr, citation.base_citation())
        elif cite_type == 'state_regional':
            if not getattr(cluster, 'state_cite_regional'):
                setattr(cluster, 'state_cite_regional', citation.base_citation())
        elif cite_type == 'scotus_early':
            if not getattr(cluster, 'scotus_early_cite'):
                setattr(cluster, 'scotus_early_cite', citation.base_citation())
        elif cite_type == 'specialty_lexis':
            if not getattr(cluster, 'lexis_cite'):
                setattr(cluster, 'lexis_cite', citation.base_citation())
        elif cite_type == 'specialty_west':
            if not getattr(cluster, 'westlaw_cite'):
                setattr(cluster, 'westlaw_cite', citation.base_citation())
        elif cite_type == 'neutral':
            if not getattr(cluster, 'neutral_cite'):
                setattr(cluster, 'neutral_cite', citation.base_citation())

    def handle_edge(self, node, neighbor, data, options):
        """Add an edge to the database if it's significant."""
        if data['weight'] > EDGE_RELEVANCE_THRESHOLD:
            # Look up both citations.
            node_results = self.match_on_citation(node)
            neighbor_results = self.match_on_citation(neighbor)

            # If neither returns a result, do nothing.
            if not node_results and not neighbor_results:
                return

            # If both citations load results, do nothing. In this case, the
            # results could be the same or they could be different. Either way,
            # we don't want to deal with them.
            if node_results and neighbor_results:
                return

            # If one citation loads something and the other doesn't, we're in
            # business.
            if len(node_results) == 1 or len(neighbor_results) == 1:
                if node_results:
                    # Update using the citation from neighbor
                    cluster = OpinionCluster.objects.get(
                        pk=node_results[0].cluster_id
                    )
                    self.add_citation_to_cluster(
                        neighbor,
                        cluster,
                    )

                elif neighbor_results:
                    # Update using the citation from node
                    cluster = OpinionCluster.objects.get(
                        pk=neighbor_results[0].cluster_id
                    )
                    self.add_citation_to_cluster(
                        node,
                        cluster,
                    )

            if options['update_database']:
                cluster.save()

    def add_groups_to_network(self, citation_groups):
        """Add the citation groups from an opinion to the global network
        object, normalizing the Citation objects.
        """
        for group in citation_groups:
            edge_list = make_edge_list(group)
            for edge in edge_list:
                # Strip extraneous attributes so that nx equality works.
                edge = [c.strip_attributes() for c in edge]
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
            sys.stdout.write("\nSolr index not updated. You may want to do so "
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

        sys.stdout.write("Entering phase one: Building a network object of all "
                         "citations.\n")
        q = Opinion.objects.all()
        if options.get('doc_id'):
            q = q.filter(pk__in=options['doc_id'])
        count = q.count()
        completed = 0
        opinions = queryset_generator(q, chunksize=10000)

        for o in opinions:
            citations = get_document_citations(o)
            citation_groups = identify_parallel_citations(citations)
            self.add_groups_to_network(citation_groups)
            completed += 1
            sys.stdout.write("\r  Completed %s of %s." % (completed, count))
        sys.stdout.write("\n")
        pprint.pprint([node.base_citation() for node in self.g.nodes()])
        print
        for node, neighbor, data in self.g.edges(data=True):
            print "Weight: %s" % data
            print u"  %s\t%s" % (node.base_citation(), str(node).decode('utf-8'))
            print u"  %s\t%s" % (neighbor.base_citation(), str(neighbor).decode('utf-8'))

        sys.stdout.write("Entering phase two: Saving the best edges to the "
                         "database.\n")
        for node, neighbor, data in self.g.edges(data=True):
            self.handle_edge(node, neighbor, data, options)


        self.do_solr(options)
