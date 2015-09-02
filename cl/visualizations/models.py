# coding=utf-8
import networkx
import time

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db import models
from django.utils.text import slugify

from cl.lib.string_utils import trunc
from cl.search.models import OpinionCluster


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

    def _build_graph(self, root_authority, max_depth=6):
        """Recursively build a networkx graph

        Process is:
         - Work backwards through the authorities for self.cluster_end and all
           of its children.
         - For each authority, add it to a networkx graph, if:
            - it happened after self.cluster_start
            - it's in the Supreme Court
            - we haven't exceeded a max_depth of six cases.
            - we haven't already followed this path
        """
        g = networkx.Graph()
        is_cluster_start_obj = (root_authority == self.cluster_start)
        if max_depth > 0 and not is_cluster_start_obj:
            # Make sure that we never try to get authorities for the start
            # cluster.
            assert root_authority.pk != self.cluster_start_id
            for authority in root_authority.authorities.filter(
                    docket__court='scotus',
                    date_filed__gte=self.cluster_start.date_filed):

                g.add_edge(root_authority.pk, authority.pk)
                # Combine our present graph with the result of the next
                # recursion
                g = networkx.compose(g, self._build_graph(
                    authority,
                    max_depth - 1,
                ))

        return g

    def add_clusters(self):
        """Do the network analysis to add clusters to the model.

        Process is to:
         - Build a networkx graph
         - For all nodes in the graph, add them to self.clusters
        """
        t1 = time.time()
        g = self._build_graph(
            self.cluster_end,
            max_depth=6,
        )

        # Add all items to self.clusters
        self.clusters.add(*g.nodes())

        t2 = time.time()
        self.generation_time = t2 - t1
        self.save()

    def __unicode__(self):
        return '{pk}: {title}'.format(self.pk, self.title)

    def get_absolute_url(self):
        return reverse('view_visualization', kwargs={'pk': self.pk,
                                                     'slug': self.slug})

    def save(self, *args, **kwargs):
        if self.pk is None:
            if not self.title:
                self.title = trunc(self.make_title(), 200, ellipsis='…')
            self.slug = trunc(slugify(self.title), 75)
        super(SCOTUSMap, self).save(*args, **kwargs)


class JSONVersions(models.Model):
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
