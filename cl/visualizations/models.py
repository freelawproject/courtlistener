# coding=utf-8
import json

import itertools
import logging
import networkx
import time

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.text import slugify

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

    def _build_digraph(self, root_authority, visited_nodes, good_nodes,
                       max_depth, max_nodes=70):
        """Recursively build a networkx graph

        Process is:
         - Work backwards through the authorities for self.cluster_end and all
           of its children.
         - For each authority, add it to a networkx graph, if:
            - it happened after self.cluster_start
            - it's in the Supreme Court
            - we haven't exceeded max_depth cases.
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
        if len(good_nodes) == 0:
            # Add the start point
            good_nodes.add(self.cluster_start_id)

        logger.info("Now using root_authority of: %s, and max_depth of %s." % (
            root_authority,
            max_depth,
        ))
        g = networkx.DiGraph()

        is_cluster_start_obj = (root_authority == self.cluster_start)
        is_already_handled = (root_authority.pk in visited_nodes)
        is_past_max_depth = (max_depth == 0)
        blocking_conditions = [
            is_cluster_start_obj,
            is_already_handled,
            is_past_max_depth,
        ]
        logger.info(
            "Blocking conditions are:\n"
            "  is_cluster_start_obj: %s\n"
            "  is_already_handled:   %s\n"
            "  is_past_max_depth:    %s" % (
                is_cluster_start_obj,
                is_already_handled,
                is_past_max_depth
        ))
        if not any(blocking_conditions):
            # Python passes objects by reference, so updating it here takes
            # care of updating the variable in all the recursive calls. More
            # discussion: http://stackoverflow.com/q/32361493/64911
            visited_nodes.add(root_authority.pk)
            logger.info("We have visited %s unique nodes so far." % len(visited_nodes))
            authorities = root_authority.authorities.filter(
                docket__court='scotus',
                date_filed__gte=self.cluster_start.date_filed
            )
            logger.info("Found %s sub_authorities to root node: %s" % (
                authorities.count(),
                root_authority,
            ))
            for authority in authorities:
                # Combine our present graph with the result of the next
                # recursion
                if authority.pk in good_nodes:
                    # This is a path to a good node in the network, such as the
                    # start node or another node that we know gets there.
                    logger.info("Found a path to a good node, %s, starting from %s" % (authority, root_authority))
                    g.add_edge(root_authority.pk, authority.pk)
                else:
                    logger.info("Haven't yet reached a good node. Recursing.")
                    sub_graph = self._build_digraph(
                        authority,
                        visited_nodes,
                        good_nodes,
                        max_depth - 1,
                        max_nodes=max_nodes,
                    )
                    logger.info("  Subgraph of %s and its children has %s nodes" % (
                        authority,
                        len(sub_graph),
                    ))
                    intersects_with_good_nodes = any([node in sub_graph for
                                                      node in good_nodes])
                    logger.info("Authority, %s, is %s hops from the end and has a max_depth of %s." % (
                        authority,
                        networkx.shortest_path_length(
                            g,
                            authority.pk,
                            self.cluster_end_id
                        ),
                        max_depth,
                    ))
                    if all([intersects_with_good_nodes]):


                        # If there is an intersection between known good nodes
                        # and the current sub_graph, merge the current sub_graph
                        # with the main graph object.
                        logger.info("  Found an intersection between current subgraph of %s nodes and our set of known good_nodes." % len(sub_graph))
                        good_nodes.add(authority.pk)
                        g.add_edge(root_authority.pk, authority.pk)
                        g = networkx.compose(g, sub_graph)
                        logger.info("    g now has %s nodes" % len(g))
                        logger.info("    good_nodes now has %s nodes" % len(good_nodes))
                    else:
                        logger.info("  Reached a dead end. Ditching subgraph of %s nodes." % len(sub_graph))

                    if len(g) > max_nodes:
                        raise TooManyNodes()

        return g

    # def _trim_branches(self, g):
    #     """Find all the paths from start to finish, and nuke any nodes that
    #     aren't in those paths.
    #
    #     See for more details: http://stackoverflow.com/questions/33586342/
    #     """
    #     all_path_nodes = set(itertools.chain(
    #         *list(networkx.all_simple_paths(g, source=self.cluster_end.pk,
    #                                         target=self.cluster_start.pk))
    #     ))
    #
    #     return g.subgraph(all_path_nodes)

    def add_clusters(self):
        """Do the network analysis to add clusters to the model.

        Process is to:
         - Build a networkx graph
         - For all nodes in the graph, add them to self.clusters
         - Update self.generation_time once complete.
        """
        t1 = time.time()
        try:
            g = self._build_digraph(
                self.cluster_end,
                set(),
                set(),
                max_depth=4,
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
            g = self._build_digraph(
                self.cluster_end,
                set(),
                set(),
                max_depth=4,
            )
            # XXX g = self._trim_branches(g)

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
