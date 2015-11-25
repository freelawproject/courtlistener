# coding=utf-8
import json

import networkx

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.text import slugify
from django.utils.timezone import now

from cl.lib.string_utils import trunc
from cl.search.models import OpinionCluster
from cl.visualizations.utils import (
    set_shortest_path_to_end, graphs_intersect, within_max_hops, TooManyNodes
)


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
    date_published = models.DateTimeField(
        help_text="The moment when the visualization was first published",
        db_index=True,
        blank=True,
        null=True,
    )
    date_deleted = models.DateTimeField(
        help_text="The moment when the visualization was last deleted",
        db_index=True,
        blank=True,
        null=True,
    )
    title = models.CharField(
        help_text="The title of the visualization that you're creating.",
        max_length=200,
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

    __original_deleted = None

    def __init__(self, *args, **kwargs):
        super(SCOTUSMap, self).__init__(*args, **kwargs)
        self.__original_deleted = self.deleted

    @property
    def json(self):
        """Returns the most recent version"""
        return self.json_versions.all()[0].json_data

    @property
    def referers_displayed(self):
        """Return good referers"""
        return self.referers.filter(display=True).order_by('date_created')

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

    def build_nx_digraph(self, parent_authority, visited_nodes, good_nodes,
                         max_hops, hops_taken=0, max_nodes=70):
        """Recursively build a networkx graph

        Process is:
         - Work backwards through the authorities for self.cluster_end and all
           of its children.
         - For each authority, add it to a nx graph, if:
            - it happened after self.cluster_start
            - it's in the Supreme Court
            - we haven't exceeded max_hops
            - we haven't already followed this path in a longer or equal route
            - it is on a simple path between the beginning and end
            - fewer than max_nodes nodes are in the network

        The last point above is a complicated one. The algorithm is implemented
        in a depth-first fashion, so we quickly can create simple paths between
        the first and last node. If it were in a breadth-first algorithm, we
        would fan out and have to do many more queries before we learned that a
        line of citations was needed or not. For example, consider this network:

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

        The other complicated part of this algorithm is keeping track of
        shortest routes and avoiding unneeded graph traversal. For example, it's
        quite possible to traverse

        :param parent_authority: The starting point for the recursion. At first,
        this will be self.cluster_end, but in recursive calls, it will be the
        child of the current parent.
        :param visited_nodes: A dict of nodes that have already been visited.
        :param good_nodes: A dict of nodes that have been identified as good.
        :param hops_taken: The number of hops taken so far, from
        self.cluster_end
        :param max_hops: The maximum degree of separation for the network.
        :param max_nodes: The maximum number of nodes a network can contain.
        """
        g = networkx.DiGraph()
        if len(good_nodes) == 0:
            # Add the beginning and end.
            good_nodes = {
                self.cluster_start_id: {'shortest_path': 0},
            }

        is_already_handled_with_shorter_path = (
            parent_authority.pk in visited_nodes and
            visited_nodes[parent_authority.pk]['hops_taken'] < hops_taken
        )
        has_no_more_hops_remaining = (hops_taken == max_hops)
        blocking_conditions = [
            is_already_handled_with_shorter_path,
            has_no_more_hops_remaining,
        ]
        if not any(blocking_conditions):
            visited_nodes[parent_authority.pk] = {'hops_taken': hops_taken}
            hops_taken += 1
            for child_authority in parent_authority.authorities.filter(
                        docket__court='scotus',
                        date_filed__gte=self.cluster_start.date_filed
                    ).order_by('date_filed'):
                # Combine our present graph with the result of the next
                # recursion
                sub_graph = networkx.DiGraph()
                if child_authority == self.cluster_start:
                    # Parent links to the starting point. Add an edge. No need
                    # to check distance here because we're already at the start
                    # node.
                    g.add_edge(parent_authority.pk, child_authority.pk)
                    _ = set_shortest_path_to_end(
                        good_nodes,
                        node_id=parent_authority.pk,
                        target_id=child_authority.pk,
                    )
                elif child_authority.pk in good_nodes:
                    # Parent links to a node already in the network. Check if we
                    # could make it to the end in max_dod hops. Set
                    # shortest_path for the child_authority
                    if within_max_hops(good_nodes, child_authority.pk,
                                       hops_taken, max_hops):
                        g.add_edge(parent_authority.pk, child_authority.pk)
                        is_shorter = set_shortest_path_to_end(
                            good_nodes,
                            node_id=parent_authority.pk,
                            target_id=child_authority.pk,
                        )
                        if is_shorter:
                            # New route to a node that's shorter than the old
                            # route. Thus, we must re-recurse its children.
                            sub_graph = self.build_nx_digraph(
                                parent_authority=child_authority,
                                visited_nodes=visited_nodes,
                                good_nodes=good_nodes,
                                max_hops=max_hops,
                                hops_taken=hops_taken,
                                max_nodes=max_nodes,
                            )
                else:
                    # No easy shortcuts. Recurse.
                    sub_graph = self.build_nx_digraph(
                        parent_authority=child_authority,
                        visited_nodes=visited_nodes,
                        good_nodes=good_nodes,
                        max_hops=max_hops,
                        hops_taken=hops_taken,
                        max_nodes=max_nodes,
                    )

                if graphs_intersect(good_nodes, g, sub_graph):
                    # The graphs intersect. Merge them.
                    g.add_edge(parent_authority.pk, child_authority.pk)
                    _ = set_shortest_path_to_end(
                        good_nodes,
                        node_id=parent_authority.pk,
                        target_id=child_authority.pk,
                    )
                    g = networkx.compose(g, sub_graph)

                if len(g) > max_nodes:
                    raise TooManyNodes()

        return g

    def add_clusters(self, g):
        """Add clusters to the model using an existing nx graph.
        """
        self.clusters.add(*g.nodes())
        self.save()

    def to_json(self, g):
        """Make a JSON representation of a NetworkX graph of the data.
        """
        j = {
            "meta": {
                "donate": "Please consider donating to support more projects "
                          "from Free Law Project",
                "version": 1.1,
            },
        }

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
                "scdb_id": cluster.scbd_id,
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

        if self.published is True and self.date_published is None:
            # First time published.
            self.date_published = now()

        if self.deleted is True and self.__original_deleted != self.deleted:
            # Item was just deleted.
            self.date_deleted = now()

        if self.pk is None:
            # First time being saved.
            self.slug = trunc(slugify(self.title), 75)
            # If we could, we'd add clusters and json here, but you can't do
            # that kind of thing until the first object has been saved.
        super(SCOTUSMap, self).save(*args, **kwargs)
        self.__original_deleted = self.deleted

    class Meta:
        permissions = (
            ('has_beta_access', 'Can access features during beta period.'),
        )


class Referer(models.Model):
    """Holds the referer domains where embedded maps are placed"""
    map = models.ForeignKey(
        SCOTUSMap,
        help_text="The visualization that was embedded and which generated a "
                  "referer",
        related_name='referers',
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The time when this item was modified",
        auto_now=True,
        db_index=True,
    )
    url = models.URLField(
        help_text="The URL where this item was embedded.",
        max_length="3000",
        db_index=True,
    )
    page_title = models.CharField(
        help_text="The title of the page where the item was embedded",
        max_length=500,
        blank=True,
    )
    display = models.BooleanField(
        help_text="Should this item be displayed?",
        default=False,
    )

    class Meta:
        # Ensure that we don't have dups in the DB for a given map.
        unique_together = (("map", "url"),)


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

    def __unicode__(self):
        return '<JSONVersion {pk}> for <{map}>'.format(
            pk=getattr(self, 'pk', None),
            map=self.map,
        )

    class Meta:
        ordering = ['-date_modified']
