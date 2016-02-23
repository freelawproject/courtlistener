# coding=utf-8
"""
Functional tests for the Visualization feature of CourtListener
"""
from django.contrib.auth.models import User, Permission
from django.core.urlresolvers import reverse
from cl.users.models import UserProfile
from cl.tests.base import BaseSeleniumTest


class VisualizationCrudTests(BaseSeleniumTest):
    """
    Test CRUD operations from the browser point of view
    """

    fixtures = ['scotus_map_data.json', 'visualizations.json']

    def setUp(self):
        self.beta_user = User.objects.create_user(
            'beta', 'beta@cl.com', 'password'
        )
        permission = Permission.objects.get(
            codename='has_beta_access'
        )
        self.beta_user.user_permissions.add(permission)
        self.beta_user.save()
        self.beta_user = UserProfile.objects.create(
            user=self.user,
            email_confirmed=True
        )
        super(VisualizationCrudTests, self).setUp()

    def test_creating_new_visualization(self):
        """ Test if a user can create a new Visualization """
        # Beth Beta-User logs into CL
        self.attempt_sign_in('beta', 'password')

        # She selects "New Visualization" from the new Visualization menu

        # Once there, she notices inputs for a First and Second Case

        # For the First Case, she starts typing 'Marsh'

        # She notices a drop down from the type-ahead search!

        # She selects the case she was thinking of: 'Marsh v. Chambers'

        # For the Second Case, she starts typing 'Cutter'

        # In the new type-ahead, selects the Jon B. Cutter case

        # She notices a "More Options" button and, why not, she clicks it

        # Wow, looks like she can enter a Title and Description

        # She clicks Make this Network when she's done

        # And she's brought to the new Visualization she just created!