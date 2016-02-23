"""
Unit tests for Visualizations
"""
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from cl.visualizations.forms import VizForm
from cl.visualizations.models import SCOTUSMap, JSONVersion
from cl.visualizations import utils, views
from cl.users.models import UserProfile
from cl.search.models import OpinionCluster


class TestVizUtils(TestCase):
    """ Tests for Visualization app utils """

    fixtures = ['scotus_map_data.json']

    def test_reverse_endpoints_does_not_reverse_good_inputs(self):
        """
        Test the utility function does not change the order of endpoints that
        are already in correct order
        """
        start = OpinionCluster.objects.get(
            case_name='Marsh v. Chambers'
        )
        end = OpinionCluster.objects.get(
            case_name='Town of Greece v. Galloway'
        )
        new_start, new_end = utils.reverse_endpoints_if_needed(start, end)
        self.assertEqual(new_start, start)
        self.assertEqual(new_end, end)

    def test_reverse_endpoints_reverses_backwards_inputs(self):
        """
        Test the utility function for properly ordering visualization
        endpoints.
        """
        real_end = OpinionCluster.objects.get(
            case_name='Town of Greece v. Galloway'
        )
        real_start = OpinionCluster.objects.get(
            case_name='Marsh v. Chambers'
        )
        reversed_start, reversed_end = utils.reverse_endpoints_if_needed(
            real_end,
            real_start
        )
        self.assertEqual(real_start, reversed_start)
        self.assertEqual(real_end, reversed_end)


class TestVizModels(TestCase):
    """ Tests for Visualization models """

    # This fixture is pretty bloated. TODO: Slim down fixture file later.
    fixtures = ['scotus_map_data.json', 'visualizations.json']

    def setUp(self):
        self.user = User.objects.create_user('Joe', 'joe@cl.com', 'password')
        self.start = OpinionCluster.objects.get(
            case_name='Town of Greece v. Galloway'
        )
        self.end = OpinionCluster.objects.get(
            case_name='Marsh v. Chambers'
        )

    def test_SCOTUSMap_builds_nx_digraph(self):
        """ Tests build_nx_digraph method to see how it works """
        viz = SCOTUSMap(
            user=self.user,
            cluster_start=self.start,
            cluster_end=self.end,
            title='Test SCOTUSMap',
            notes='Test Notes'
        )

        build_kwargs = {
            'parent_authority': self.end,
            'visited_nodes': {},
            'good_nodes': {},
            'max_hops': 3,
        }

        g = viz.build_nx_digraph(**build_kwargs)
        self.assertTrue(g.edges() > 0)

    def test_SCOTUSMap_deletes_cascade(self):
        """
        Make sure we delete JSONVersion instances when deleted SCOTUSMaps
        """
        viz = SCOTUSMap.objects.get(pk=1)
        json_version = JSONVersion.objects.get(map=viz.pk)
        self.assertIsNotNone(json_version)
        json_pk = json_version.pk

        viz.delete()

        with self.assertRaises(JSONVersion.DoesNotExist):
            JSONVersion.objects.get(pk=json_pk)


class TestViews(TestCase):
    """ Tests for Visualization views """

    view = 'new_visualization'

    fixtures = ['scotus_map_data.json', 'visualizations.json']

    def setUp(self):
        self.start = OpinionCluster.objects.get(
            case_name='Town of Greece v. Galloway'
        )
        self.end = OpinionCluster.objects.get(
            case_name='Marsh v. Chambers'
        )
        self.user = User.objects.create_user('user', 'user@cl.com', 'password')
        self.user.save()
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            email_confirmed=True
        )

    def test_new_visualization_view_redirects_non_beta_users(self):
        """ Non-beta users should get sent away """
        response = self.client.get(reverse(self.view))
        self.assertEqual(response.status_code, 302)

    def test_new_visualization_view_provides_form(self):
        """ Test a GET to the Visualization view provides a VizForm """
        self.client.login(username='user', password='password')
        response = self.client.get(reverse(self.view))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['form'], VizForm)

    def test_new_visualization_view_creates_map_on_post(self):
        """ Test a valid POST creates a new ScotusMap object """
        SCOTUSMap.objects.all().delete()

        self.client.login(username='user', password='password')
        data = {
            'cluster_start': 2674862,
            'cluster_end': 111014,
            'title': 'Test Map Title',
            'notes': 'Just some notes'
        }
        response = self.client.post(reverse(self.view), data=data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(1, SCOTUSMap.objects.count())
        scotus_map = SCOTUSMap.objects.get(title='Test Map Title')
        self.assertIsNotNone(scotus_map)

    def test_published_visualizations_show_in_gallery(self):
        """ Test that a user can see published visualizations from others """
        self.client.login(username='user', password='password')
        response = self.client.get(reverse('viz_gallery'))
        html = response.content.decode('utf-8')
        self.assertIn('Shared by Admin', html)
        self.assertIn('FREE KESHA', html)

    def test_cannot_view_anothers_private_visualization(self):
        """ Test unpublished visualizations cannot be seen by others """
        viz = SCOTUSMap.objects.get(pk=2)
        self.assertFalse(viz.published, 'Test SCOTUSMap should be unpublished')
        url = reverse(
            'view_visualization', kwargs={'pk': viz.pk, 'slug': viz.slug}
        )

        self.client.login(username='admin', password='password')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'My Private Visualization', response.content)

        self.client.login(username='user', password='password')
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn(b'My Private Visualization', response.context)

    def test_view_counts_increment_by_one(self):
        """ Test the view count for a Visualization increments on page view """
        viz = SCOTUSMap.objects.get(pk=1)
        old_view_count = viz.view_count

        self.client.login(username='user', password='password')
        response = self.client.get(viz.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            old_view_count + 1,
            SCOTUSMap.objects.get(pk=1).view_count
        )


class TestVizAjaxCrud(TestCase):
    """
    Test the CRUD operations for Visuzalizations that the javascript client
    code relies on currently.
    """

    fixtures = ['scotus_map_data.json', 'visualizations.json']

    def setUp(self):
        self.live_viz = SCOTUSMap.objects.get(pk=1)
        self.private_viz = SCOTUSMap.objects.get(pk=2)
        self.deleted_viz = SCOTUSMap.objects.get(pk=3)
        self.factory = RequestFactory()

    def _build_post(self, url, username=None, data=None):
        """ Helper method to build authenticated AJAX POST
        Args:
            url: url pattern to request
            username: username for User to attach
            **data: dictionary of POST data

        Returns: HttpRequest configured as an AJAX POST
        """
        if not data:
            data = {}
        post = self.factory.post(url, data=data)
        if username:
            post.user = User.objects.get(username=username)
        post.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        return post

    def post_ajax_view(self, view, pk, username='admin'):
        """
        Generates a simple POST for the given view with the given
        private key as the POST data.

        Args:
            view: reference to Django View
            pk: private key of target SCOTUSMap
            username: username of User to POST as

        Returns: new reference to updated SCOTUSMap

        """
        post = self._build_post(
            reverse(view),
            username=username,
            data={'pk': pk}
        )
        response = view(post)
        self.assertEqual(response.status_code, 200)
        return SCOTUSMap.objects.get(pk=pk)

    def test_deletion_via_ajax_view(self):
        """
        Test deletion of visualization via view only sets deleted flag and
        doesn't actualy delete the object yet
        """
        self.assertFalse(self.live_viz.deleted)
        self.assertIsNone(self.live_viz.date_deleted)

        viz = self.post_ajax_view(views.delete_visualization, self.live_viz.pk)

        self.assertTrue(viz.deleted)
        self.assertIsNotNone(viz.date_deleted)

    def test_restore_via_ajax_view(self):
        """
        Tests restoration of deleted visualization from teh trash via a
        ajax POST
        """
        self.assertTrue(self.deleted_viz.deleted)
        self.assertIsNotNone(self.deleted_viz.date_deleted)

        viz = self.post_ajax_view(
            views.restore_visualization, self.deleted_viz.pk
        )

        self.assertFalse(viz.deleted)
        self.assertIsNone(viz.date_deleted)

    def test_privatizing_via_ajax_view(self):
        """
        Tests setting a public visualization to private via an AJAX POST
        """
        self.assertTrue(self.live_viz.published)
        self.assertIsNotNone(self.live_viz.date_published)

        viz = self.post_ajax_view(
            views.privatize_visualization, self.live_viz.pk
        )

        self.assertFalse(viz.published)

    def test_sharing_via_ajax_view(self):
        """
        Tests sharing a public visualization via an AJAX POST
        """
        self.assertFalse(self.private_viz.published)
        self.assertIsNone(self.private_viz.date_published)

        viz = self.post_ajax_view(
            views.share_visualization, self.private_viz.pk
        )

        self.assertTrue(viz.published)
        self.assertIsNotNone(viz.date_published)
