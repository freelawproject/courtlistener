# coding=utf-8
import json

import logging
import networkx
import time

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.text import slugify
from networkx.exception import NetworkXError

from cl.lib.string_utils import trunc
from cl.search.models import OpinionCluster

logger = logging.getLogger(__name__)


class TooManyNodes(Exception):
    class SetupException(Exception):
        def __init__(self, message):
            Exception.__init__(self, message)


class SCOTUSMap(models.Model):
    user = models.ForeignKey(
        User,
        help_text="The user that owns the visualization",
        related_name="scotus_maps",
    )
    cluster_start = models.ForeignKey(
        OpinionCluster,
        help_text="The starting cluster for the visualization",
        related_name='visualizations_starting_here',
    )
    cluster_end = models.ForeignKey(
        OpinionCluster,
        help_text="The ending cluster for the visualization",
        related_name='visualizations_ending_here',
    )
    clusters = models.ManyToManyField(
        OpinionCluster,
        help_text="The clusters involved in this visualization, including the "
                  "start and end clusters.",
        related_name="visualizations",
        blank=True,
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    title = models.CharField(
        help_text="The title of the visualization that you're creating.",
        max_length=200,
    )
    subtitle = models.CharField(
        help_text="The subtitle of the visualization that you're creating.",
        max_length=300,
        blank=True,
    )
    slug = models.SlugField(
        help_text="The URL path that the visualization will map to (the slug)",
        max_length=75,
    )
    notes = models.TextField(
        help_text="Any notes that help explain the diagram, in Markdown format",
        blank=True,
    )
    view_count = models.IntegerField(
        help_text="The number of times the visualization has been seen.",
        default=0,
    )
    published = models.BooleanField(
        help_text="Whether the visualization can be seen publicly.",
        default=False,
    )
    deleted = models.BooleanField(
        help_text="Has a user chosen to delete this visualization?",
        default=False,
    )
    generation_time = models.FloatField(
        help_text="The length of time it takes to generate a visuzalization, "
                  "in seconds.",
        default=0,
    )

    @property
    def json(self):
        """Returns the most recent version"""
        return self.json_versions.all()[0].json_data

    def make_title(self):
        """Make a title for the visualization

        Title tries to use the shortest possible case name from the starting
        and ending clusters plus the number of degrees.
        """
        def get_best_case_name(obj):
            case_name_preference = [
                obj.case_name_short,
                obj.case_name,
                obj.case_name_full
            ]
            return next((_ for _ in case_name_preference if _), "Unknown")

        return "{start} to {end}".format(
            start=get_best_case_name(self.cluster_start),
            end=get_best_case_name(self.cluster_end),
        )

    def __update_hops_taken(self, good_nodes, node_id, hops_taken_this_time):
        if node_id in good_nodes:
            hops_taken_last_time = good_nodes[node_id]['hops_taken']
            good_nodes[node_id]['hops_taken'] = min(
                hops_taken_this_time,
                hops_taken_last_time,
            )
        else:
            good_nodes[node_id] = {'hops_taken': hops_taken_this_time}

    def __within_max_dos(self, good_nodes, child_authority_id,
                         hops_taken_this_time, max_dos):
        """Determine if a new route to a node that's already in the network
        is within the max_dos of the start point.
        """
        # This is a new path to a node that's already in the network. Add it
        # if it wouldn't take too many hops.
        hops_taken_last_time = good_nodes[child_authority_id]['hops_taken']
        if (hops_taken_last_time + hops_taken_this_time) <= max_dos or \
                (hops_taken_this_time <= hops_taken_last_time):
            return True
        return False

    def __graphs_intersect(self, good_nodes, main_graph, sub_graph):
        """Test if two graphs have common nodes.

        First check if it's in the main graph, then check if it's in good_nodes,
        indicating a second path to the start node.
        """
        return (any([(node in main_graph) for node in sub_graph.nodes()]) or
                any([(node in good_nodes) for node in sub_graph.nodes()]))

    def _build_digraph(self, parent_authority, visited_nodes, good_nodes,
                       max_dos, hops_taken=0, max_nodes=700):
        """Recursively build a nx graph

        Process is:
         - Work backwards through the authorities for self.cluster_end and all
           of its children.
         - For each authority, add it to a nx graph, if:
            - it happened after self.cluster_start
            - it's in the Supreme Court
            - we haven't exceeded max_dos
            - we haven't already followed this path
            - it is on a simple path between the beginning and end
            - fewer than max_nodes nodes are in the network

        The last point above is a complicated one. The algorithm below is
        implemented in a depth-first fashion, so we quickly can create simple
        paths between the first and last node. If it were in a breadth-first
        algorithm, we would fan out and have to do many more queries before we
        learned that a line of citations was needed or not. For example,
        consider this network:

            START
               ├─-> A--> B--> C--> D--> END
               └--> E    ├─-> F
                         └--> G

        The only nodes that we should include are A, B, C, and D. In a depth-
        first approach, you do:

            START
               ├─1-> A-2-> B-3-> C-4-> D-5-> END
               └-8-> E     ├─6-> F
                           └-7-> G

        After five hops, we know that A, B, C, and D are relevant and should be
        kept.

        Compare to a breadth-first:

             START
                ├─1-> A-3-> B-4-> C-7-> D-8-> END
                └-2-> E     ├─5-> F
                            └-6-> G

        In this case, it takes eight hops to know the same thing, and in a real
        network, it would be many more than two or three citations from each
        node.

        This matters a great deal because the sooner we can count the number of
        nodes in the network, the sooner we will hit max_nodes and be able to
        abort if the job is too big.
        """
        g = networkx.DiGraph()
        if len(good_nodes) == 0:
            # Add the beginning and end.
            good_nodes = {
                self.cluster_end_id: {'hops_taken': 0},
                self.cluster_start_id: {'hops_taken': 4},
            }
        hops_taken += 1

        is_cluster_start_obj = (parent_authority == self.cluster_start)
        is_already_handled = (parent_authority in visited_nodes)
        has_no_more_hops_remaining = (hops_taken > max_dos)
        blocking_conditions = [
            is_cluster_start_obj,
            is_already_handled,
            has_no_more_hops_remaining,
        ]
        if not any(blocking_conditions):
            visited_nodes.add(parent_authority)
            child_authorities = parent_authority.authorities.filter(
                docket__court='scotus',
                date_filed__gte=self.cluster_start.date_filed
            )
            for child_authority in child_authorities:
                # Combine our present graph with the result of the next
                # recursion
                if child_authority == self.cluster_start:
                    print "Reached cluster_start with child_authority: %s and parent_authority: %s" % (child_authority, parent_authority)
                    # Parent links to the starting point. Add an edge. No need
                    # to check distance here because we're already at the start
                    # node.
                    g.add_edge(parent_authority.pk, child_authority.pk)
                    self.__update_hops_taken(good_nodes, child_authority.pk,
                                             hops_taken)

                elif child_authority.pk in good_nodes:
                    # Parent links to a node already in the network. Check if we
                    # could make it to the end in max_dod hops. Update
                    # hops_taken if necessary.
                    if self.__within_max_dos(good_nodes, child_authority.pk,
                                             hops_taken, max_dos):
                        g.add_edge(parent_authority.pk, child_authority.pk)
                        self.__update_hops_taken(good_nodes, child_authority.pk,
                                                 hops_taken)
                else:
                    # No easy shortcuts. Recurse.
                    sub_graph = self._build_digraph(
                        parent_authority=child_authority,
                        visited_nodes=visited_nodes,
                        good_nodes=good_nodes,
                        max_dos=max_dos,
                        hops_taken=hops_taken,
                        max_nodes=max_nodes,
                    )

                    if len(sub_graph) > 0:
                        print "Subgraph has %s nodes" % len(sub_graph)
                        print "g has %s nodes" % len(g)
                    if self.__graphs_intersect(good_nodes, g, sub_graph):
                        # The graphs intersect. Merge them.
                        print "The graphs intersected!"
                        g.add_edge(parent_authority.pk, child_authority.pk)
                        self.__update_hops_taken(good_nodes, child_authority.pk,
                                                 hops_taken)
                        g = networkx.compose(g, sub_graph)
                    else:
                        print "The graphs didn't intersect. Boo."

                if len(g) > max_nodes:
                    raise TooManyNodes()

        return g

    def add_clusters(self):
        """Do the network analysis to add clusters to the model.

        Process is to:
         - Build a nx graph
         - For all nodes in the graph, add them to self.clusters
         - Update self.generation_time once complete.
        """
        t1 = time.time()
        try:
            g = self._build_digraph(
                parent_authority=self.cluster_end,
                visited_nodes=set(),
                good_nodes=dict(),
                max_dos=4,
            )
        except TooManyNodes, e:
            logger.warn("Too many nodes while building "
                            "visualization %s" % self.pk)

        # Add all items to self.clusters
        self.clusters.add(*g.nodes())

        t2 = time.time()
        self.generation_time = t2 - t1
        self.save()

        return g

    def to_json(self, g=None):
        """Make a JSON representation of self

        :param g: Optionally, you can provide a network graph. If provided, it
        will be used instead of generating one anew.
        """
        j = {
            "meta": {
                "donate": "Please consider donating to support more projects "
                          "from Free Law Project",
                "version": 1.0,
            },
        }
        if g is None:
            # XXX build the digraph here if you want to.
            # XXX g = self._trim_branches(g)
            pass

        opinion_clusters = []
        for cluster in self.clusters.all():
            opinions_cited = {}
            for node in g.neighbors(cluster.pk):
                opinions_cited[node] = {'opacitiy': 1}

            opinion_clusters.append({
                "id": cluster.pk,
                "absolute_url": cluster.get_absolute_url(),
                "case_name": cluster.case_name,
                "case_name_short": cluster.case_name_short,
                "citation_count": g.in_degree(cluster.pk),
                "date_filed": cluster.date_filed.isoformat(),
                "decision_direction": cluster.scdb_decision_direction,
                "votes_majority": cluster.scdb_votes_majority,
                "votes_minority": cluster.scdb_votes_minority,
                "sub_opinions": [{
                    "type": "combined",
                    "opinions_cited": opinions_cited,
                }]
            })

        j['opinion_clusters'] = opinion_clusters

        return json.dumps(j, indent=2)

    def __unicode__(self):
        return '{pk}: {title}'.format(
            pk=getattr(self, 'pk', None),
            title=self.title
        )

    def get_absolute_url(self):
        return reverse('view_visualization', kwargs={'pk': self.pk,
                                                     'slug': self.slug})

    def save(self, *args, **kwargs):
        # Note that the title needs to be made first, so that the slug can be
        # generated from it.
        if not self.title:
            self.title = trunc(self.make_title(), 200, ellipsis='…')
        if self.pk is None:
            self.slug = trunc(slugify(self.title), 75)
            # If we could, we'd add clusters and json here, but you can't do
            # that kind of thing until the first object has been saved.
        super(SCOTUSMap, self).save(*args, **kwargs)


class JSONVersion(models.Model):
    """Used for holding a variety of versions of the data."""
    map = models.ForeignKey(
        SCOTUSMap,
        help_text='The visualization that the json is affiliated with.',
        related_name="json_versions",
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    json_data = models.TextField(
        help_text="The JSON data for a particular version of the visualization.",
    )

    class Meta:
        ordering = ['-date_modified']
