from datetime import datetime

import pytest
import time_machine
from django.core import mail
from django.core.management import call_command
from waffle.testutils import override_switch

from cl.lib.redis_utils import get_redis_interface
from cl.stats.models import Event
from cl.stats.utils import get_milestone_range, tally_stat
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory


class MilestoneTests(TestCase):
    def test_milestone_ranges(self) -> None:
        numbers = get_milestone_range("XS", "SM")
        self.assertEqual(numbers[0], 1e1)
        self.assertEqual(numbers[-1], 5e4)


class PartnershipEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.api_user = UserFactory()
        cls.webhook_user = UserFactory()

    def test_command_can_filter_user_api_events(self) -> None:
        with time_machine.travel(
            datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
            tick=False,
        ):
            global_v4_api_event = Event.objects.create(
                description="API v4 has logged 1000 total requests."
            )
            global_v3_api_event = Event.objects.create(
                description="API v3 has logged 1000 total requests."
            )
            global_webhook_event = Event.objects.create(
                description="Webhooks have logged 1000 total successful events."
            )
            v4_api_user_event = Event.objects.create(
                description=f"User '{self.api_user.username}' has placed their 3rd API v4 request.",
                user=self.api_user,
            )
            v3_api_user_event = Event.objects.create(
                description=f"User '{self.api_user.username}' has placed their 3rd API v3 request.",
                user=self.api_user,
            )
            webhook_user_event = Event.objects.create(
                description=f"User '{self.api_user.username}' has placed their 3rd webhook event.",
                user=self.webhook_user,
            )
            call_command("send_events_email")

        # Assert an email was sent
        self.assertEqual(
            len(mail.outbox), 1, msg="Outgoing emails don't match."
        )
        email = mail.outbox[0]

        # Extract email content
        body = email.body

        # Should include global and webhook user events
        self.assertIn(global_v3_api_event.description, body)
        self.assertIn(global_v4_api_event.description, body)
        self.assertIn(v3_api_user_event.description, body)
        self.assertIn(global_webhook_event.description, body)
        self.assertIn(webhook_user_event.description, body)

        # Should exclude v4 API user-specific event
        self.assertNotIn(v4_api_user_event.description, body)


@pytest.mark.django_db
@override_switch("increment-stats", active=True)
class StatTests(TestCase):
    def setUp(self):
        self.r = get_redis_interface("STATS")
        key = self.r.keys("test*")
        if key:
            self.r.delete(*key)

    def test_tally_a_stat(self) -> None:
        count = tally_stat("test")
        self.assertEqual(count, 1)

    def test_increment_a_stat(self) -> None:
        count = tally_stat("test2")
        self.assertEqual(count, 1)
        count = tally_stat("test2")
        self.assertEqual(count, 2)

    def test_increment_by_two(self) -> None:
        count = tally_stat("test3", inc=2)
        self.assertEqual(count, 2)
        count = tally_stat("test3", inc=2)
        self.assertEqual(count, 4)
