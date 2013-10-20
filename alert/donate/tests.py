from datetime import timedelta
from django.core import mail
from django.test import TestCase
from django.utils.timezone import now
from alert.donate.management.commands.cl_send_donation_reminders import Command
from alert.donate.models import Donation


class EmailCommandTest(TestCase):
    fixtures = ['donate_test_data.json']

    def test_sending_an_email(self):
        """Do we send emails correctly?"""
        # Set this value since the JSON will get stale and can't have dynamic dates.
        about_a_year_ago = now() - timedelta(days=355)
        Donation.objects.filter(pk=1).update(date_created=about_a_year_ago)

        comm = Command()
        comm.handle()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('you donated $1', mail.outbox[0].body)
        self.assertIn('you donated $1', mail.outbox[0].alternatives[0][0])
