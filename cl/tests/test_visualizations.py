# coding=utf-8
"""
Functional tests for the Visualization feature of CourtListener
"""
from django.contrib.auth.models import User
from cl.users.models import UserProfile
from cl.tests.base import BaseSeleniumTest


class VisualizationCrudTests(BaseSeleniumTest):
    """
    Test CRUD operations from the browser point of view
    """

    fixtures = ['scotus_map_data.json', 'visualizations.json']

    def setUp(self):
        self.user = User.objects.create_user(
            'user', 'user@cl.com', 'password'
        )
        self.user.save()
        self.user = UserProfile.objects.create(
            user=self.user,
            email_confirmed=True
        )
        super(VisualizationCrudTests, self).setUp()

    def test_creating_new_visualization(self):
        """ Test if a user can create a new Visualization """
        # Beth Beta-User logs into CL
        self.browser.get(self.server_url)
        self.attempt_sign_in('user', 'password')

        # She selects "New Visualization" from the new Visualization menu
        menu = self.browser.find_element_by_link_text('Visualizations ')
        menu.click()
        menu_item = self.browser.find_element_by_link_text('New Network')
        menu_item.click()
        self.assertIn('Create a New Citation Network', self.browser.title)

        # Once there, she notices inputs for a First and Second Case
        self.assert_text_in_body('Create a New Citation Network')
        self.assert_text_in_body('First Case')
        self.assert_text_in_body('Second Case')

        # For the First Case, she starts typing 'Marsh'
        first_case = self.browser.find_element_by_id(
            'starting-cluster-typeahead'
        )

        type_ahead = self.browser.find_element_by_css_selector('.tt-dataset-0')
        first_case.send_keys('Marsh')
        suggestion = type_ahead.find_element_by_css_selector('.tt-suggestion')
        # She notices a drop down from the type-ahead search!
        suggestion_text = suggestion.text
        self.assertIn('Marsh v. Chambers', suggestion_text)

        # She selects the case she was thinking of: 'Marsh v. Chambers'
        suggestion.click()

        # And the new case name is now in the input!
        first_case = self.browser.find_element_by_id(
            'starting-cluster-typeahead'
        )
        self.assertIn(suggestion_text, first_case.get_attribute('value'))

        # For the Second Case, she starts typing 'Cutter'
        second_case = self.browser.find_element_by_id(
            'ending-cluster-typeahead-search'
        )
        type_ahead = self.browser.find_element_by_css_selector('.tt-dataset-1')
        second_case.send_keys('Cutter')
        suggestion = type_ahead.find_element_by_css_selector('.tt-suggestion')

        # In the new type-ahead, selects the Jon B. Cutter case
        suggestion_text = suggestion.text
        self.assertIn('JON B. CUTTER', suggestion_text)
        suggestion.click()
        second_case = self.browser.find_element_by_id(
            'ending-cluster-typeahead-search'
        )
        self.assertIn(suggestion_text, second_case.get_attribute('value'))

        # She notices a "More Options" button and, why not, she clicks it
        more = self.browser.find_element_by_id('more')
        self.assertIn('More Options', more.text)

        self.assert_text_not_in_body('Title')
        self.assert_text_not_in_body('Description')
        more.click()

        # Wow, looks like she can enter a Title and Description
        self.assert_text_in_body('Title')
        title = self.browser.find_element_by_id('id_title')
        title.send_keys('Selenium Test Visualization')

        self.assert_text_in_body('Description')
        description = self.browser.find_element_by_id('id_notes')
        description.send_keys('Test description.\n#FreeKe$ha')

        # She clicks Make this Network when she's done
        self.browser.find_element_by_id('make-viz-button').click()

        # And she's brought to the new Visualization she just created!
        self.assertIn('Network Graph of Selenium', self.browser.title)
