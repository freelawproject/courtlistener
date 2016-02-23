"""
Unit tests for Visualizations
"""
from django.test import TestCase
from django.contrib.auth.models import User, Permission
from django.core.urlresolvers import reverse
from cl.visualizations.forms import VizForm
from cl.visualizations.models import SCOTUSMap, JSONVersion
from cl.visualizations import utils
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
        self.user = User.objects.create_user('beta', 'beta@cl.com', 'password')
        permission = Permission.objects.get(
            codename='has_beta_access'
        )
        self.user.user_permissions.add(permission)
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
        self.client.login(username='beta', password='password')
        response = self.client.get(reverse(self.view))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['form'], VizForm)

    def test_new_visualization_view_creates_map_on_post(self):
        """ Test a valid POST creates a new ScotusMap object """
        SCOTUSMap.objects.all().delete()

        self.client.login(username='beta', password='password')
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
        self.client.login(username='beta', password='password')
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

        self.client.login(username='beta', password='password')
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn(b'My Private Visualization', response.context)

    def test_view_counts_increment_by_one(self):
        """ Test the view count for a Visualization increments on page view """
        viz = SCOTUSMap.objects.get(pk=1)
        old_view_count = viz.view_count

        self.client.login(username='beta', password='password')
        response = self.client.get(viz.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            old_view_count + 1,
            SCOTUSMap.objects.get(pk=1).view_count
        )
