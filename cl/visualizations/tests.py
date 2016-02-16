"""
Unit tests for Visualizations
"""
from django.test import TestCase
from django.contrib.auth.models import User, Permission
from django.core.urlresolvers import reverse
from cl.visualizations.forms import VizForm
from cl.users.models import UserProfile



class TestVizForm(TestCase):
    """ Tests for VizForm form """

    pass


class TestViews(TestCase):
    """ Tests for Visualization views """

    view = 'new_visualization'

    def setUp(self):
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

    def test_new_visualization_view_provides_form(self):
        """ Test a GET to the Visualization view provides a VizForm """
        self.client.login(username='beta', password='password')
        response = self.client.get(reverse(self.view))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['form'], VizForm)
