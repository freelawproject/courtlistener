"""
Unit tests for Visualizations
"""
from django.test import TestCase
from django.contrib.auth.models import User, Permission
from django.core.urlresolvers import reverse
from cl.visualizations.forms import VizForm
from cl.visualizations.models import SCOTUSMap
from cl.visualizations import views, utils
from cl.users.models import UserProfile
from cl.search.models import OpinionCluster


class TestVizUtils(TestCase):
    """ Tests for Visualization app utils """

    fixtures = ['scotus_map_data.json']

    def test_reverse_endpoints_if_needed(self):
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
    fixtures = ['scotus_map_data.json']

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


class TestVizForm(TestCase):
    """ Tests for VizForm form """

    pass


class TestViews(TestCase):
    """ Tests for Visualization views """

    view = 'new_visualization'

    fixtures = ['scotus_map_data.json']

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
        data = {
            'cluster_start': self.start.pk,
            'cluster_end': self.end.pk,
            'title': 'Test Map Title',
            'notes': 'Just some notes'
        }
        response = self.client.post(reverse(self.view), data=data)
        # self.assertRedirects(response, reverse('view_visualization'))
        self.assertEqual(1, SCOTUSMap.objects.count())
        scotus_map = SCOTUSMap.objects.get(title='Test Map Title')
        self.assertIsNotNone(scotus_map)
