import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from http import HTTPStatus
from unittest import mock

import time_machine
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from waffle.testutils import override_switch

from cl.lib.redis_utils import get_redis_interface
from cl.recap import fetch_scheduler
from cl.recap.factories import PacerFetchQueueFactory
from cl.recap.fetch_scheduler import (
    SCHEDULER_SWITCH,
    STALE_MESSAGE,
    enqueue_fetch,
    estimate_delay,
    fail_stale_fetches,
    get_court_interval_ms,
    get_courts_with_waiting_fetches,
    mark_fetch_started,
    pop_next_fetch,
    run_dispatch_cycle,
    schedule_fetch,
    set_court_rate,
)
from cl.recap.models import PROCESSING_STATUS, REQUEST_TYPE, PacerFetchQueue
from cl.recap.tasks import fetch_docket
from cl.search.factories import CourtFactory
from cl.search.models import Court
from cl.tests.cases import SimpleTestCase, TestCase
from cl.users.factories import UserFactory

COURT = "dcd"
OTHER_COURT = "canb"
BOB, JANE, CARL = 1, 2, 3
# An arbitrary starting time, in milliseconds. The scheduler takes the time
# as an argument, so these tests never depend on the real clock.
T0 = 1_000_000
# A fixed moment for the tests that go through code reading the real clock.
NOON = datetime(2026, 10, 5, 12, 0, 0)


class SchedulerRedisTestCase(SimpleTestCase):
    """Give each test its own Redis keys, and delete them afterwards.

    Tests run in parallel against one Redis, so every test gets a unique key
    prefix rather than sharing the scheduler's real one.
    """

    def setUp(self) -> None:
        """Point the scheduler at a fresh key prefix for this test."""
        super().setUp()
        prefix = f"test_recap_fetch:{uuid.uuid4().hex}"
        patcher = mock.patch.object(fetch_scheduler, "KEY_PREFIX", prefix)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._delete_keys, prefix)

    @staticmethod
    def _delete_keys(prefix: str) -> None:
        """Delete every Redis key the test created."""
        r = get_redis_interface("CACHE")
        if keys := r.keys(f"{prefix}:*"):
            r.delete(*keys)

    @staticmethod
    def _drain(start_ms: int, limit: int | None = None) -> list[int]:
        """Take every waiting request for COURT, in the order it is allowed.

        Each request is marked as started the moment it is taken, as if a
        worker were always free, and the clock moves one second per attempt.

        :param start_ms: The time of the first attempt.
        :param limit: Stop after taking this many requests.
        :return: The PKs taken, in order.
        """
        taken: list[int] = []
        now_ms = start_ms
        while (
            limit is None or len(taken) < limit
        ) and COURT in get_courts_with_waiting_fetches():
            if (fq_pk := pop_next_fetch(COURT, now_ms)) is not None:
                mark_fetch_started(COURT, fq_pk, now_ms)
                taken.append(fq_pk)
            now_ms += 1000
        return taken


@override_settings(RECAP_FETCH_DEFAULT_COURT_RATE="1/s")
class FetchSchedulerRateTest(SchedulerRedisTestCase):
    """A court is never sent requests faster than its rate."""

    def test_next_request_waits_a_full_interval_after_a_start(self) -> None:
        """Nothing else leaves until the interval since the start passes."""
        enqueue_fetch(COURT, BOB, 1, T0)
        enqueue_fetch(COURT, BOB, 2, T0)

        self.assertEqual(pop_next_fetch(COURT, T0), 1)
        mark_fetch_started(COURT, 1, T0)

        self.assertIsNone(pop_next_fetch(COURT, T0 + 999))
        self.assertEqual(pop_next_fetch(COURT, T0 + 1000), 2)

    def test_court_waits_for_the_handed_off_request_to_start(self) -> None:
        """Busy workers can't make a court's requests pile up and burst.

        The interval counts from when a request starts running, so a request
        still waiting for a worker holds its court, however long it waits.
        """
        enqueue_fetch(COURT, BOB, 1, T0)
        enqueue_fetch(COURT, BOB, 2, T0)
        an_hour_later = T0 + 60 * 60 * 1000

        self.assertEqual(pop_next_fetch(COURT, T0), 1)
        self.assertIsNone(pop_next_fetch(COURT, an_hour_later))

        mark_fetch_started(COURT, 1, an_hour_later)
        self.assertIsNone(pop_next_fetch(COURT, an_hour_later + 999))
        self.assertEqual(pop_next_fetch(COURT, an_hour_later + 1000), 2)

    def test_each_court_has_its_own_clock(self) -> None:
        """A court inside its interval doesn't hold up another court."""
        enqueue_fetch(COURT, BOB, 1, T0)
        enqueue_fetch(COURT, BOB, 2, T0)
        enqueue_fetch(OTHER_COURT, BOB, 3, T0)

        self.assertEqual(pop_next_fetch(COURT, T0), 1)
        mark_fetch_started(COURT, 1, T0)

        self.assertIsNone(pop_next_fetch(COURT, T0 + 500))
        self.assertEqual(pop_next_fetch(OTHER_COURT, T0 + 500), 3)

    def test_rate_change_applies_to_requests_already_waiting(self) -> None:
        """A court's own rate overrides the default, without a deploy."""
        enqueue_fetch(COURT, BOB, 1, T0)
        enqueue_fetch(COURT, BOB, 2, T0)
        set_court_rate(COURT, "1/5s")

        self.assertEqual(pop_next_fetch(COURT, T0), 1)
        mark_fetch_started(COURT, 1, T0)

        self.assertIsNone(pop_next_fetch(COURT, T0 + 4999))
        self.assertEqual(pop_next_fetch(COURT, T0 + 5000), 2)

        set_court_rate(COURT, None)
        self.assertEqual(get_court_interval_ms(COURT), 1000)

    def test_rate_holds_across_concurrent_processes(self) -> None:
        """Many processes asking at the same instant get one request."""
        for fq_pk in range(1, 51):
            enqueue_fetch(COURT, BOB, fq_pk, T0)

        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(
                pool.map(lambda _: pop_next_fetch(COURT, T0), range(20))
            )

        self.assertEqual([pk for pk in results if pk is not None], [1])
        self.assertEqual(results.count(None), 19)


@override_settings(RECAP_FETCH_DEFAULT_COURT_RATE="1/s")
class FetchSchedulerFairnessTest(SchedulerRedisTestCase):
    """Within a court, users take turns."""

    def test_single_request_is_not_stuck_behind_a_large_batch(self) -> None:
        """The example from the issue: Bob's 1,000 requests and Jane's one."""
        for fq_pk in range(1, 1001):
            enqueue_fetch(COURT, BOB, fq_pk, T0)
        one_minute_later = T0 + 60 * 1000
        enqueue_fetch(COURT, JANE, 5000, one_minute_later)

        taken = self._drain(one_minute_later + 1000, limit=3)

        self.assertEqual(taken, [1, 5000, 2])

    def test_users_take_turns(self) -> None:
        """Users alternate while several wait; then the rest go in order."""
        for fq_pk in (101, 102, 103, 104, 105):
            enqueue_fetch(COURT, BOB, fq_pk, T0)
        enqueue_fetch(COURT, JANE, 201, T0 + 1)
        enqueue_fetch(COURT, CARL, 301, T0 + 2)
        enqueue_fetch(COURT, CARL, 302, T0 + 2)

        taken = self._drain(T0 + 1000)

        self.assertEqual(taken, [101, 201, 301, 102, 302, 103, 104, 105])


@override_settings(RECAP_FETCH_DEFAULT_COURT_RATE="1/s")
class FetchSchedulerEstimateTest(SchedulerRedisTestCase):
    """The estimate counts the turns ahead of a newly queued request."""

    def test_single_request_behind_a_large_batch_waits_one_turn(self) -> None:
        """Jane's estimate doesn't grow with the size of Bob's batch."""
        for fq_pk in range(1, 1001):
            enqueue_fetch(COURT, BOB, fq_pk, T0)
        enqueue_fetch(COURT, JANE, 5000, T0 + 1)

        self.assertEqual(estimate_delay(COURT, JANE, T0 + 1), 1.0)

    def test_estimate_is_never_below_the_actual_wait(self) -> None:
        """The estimate assumes the worst case for the users waiting now."""
        enqueue_fetch(COURT, JANE, 201, T0)
        for fq_pk in (301, 302, 303, 304, 305):
            enqueue_fetch(COURT, CARL, fq_pk, T0 + 1)
        for fq_pk in (101, 102, 103):
            enqueue_fetch(COURT, BOB, fq_pk, T0 + 2)
        estimate = estimate_delay(COURT, BOB, T0 + 2)

        taken = self._drain(T0 + 2)
        actual_wait = taken.index(103) * 1.0

        self.assertEqual(estimate, 6.0)
        self.assertLessEqual(actual_wait, estimate)


class SchedulerDatabaseTestCase(SchedulerRedisTestCase, TestCase):
    """Scheduler tests that also need PostgreSQL rows."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create the court and users the requests belong to."""
        CourtFactory(
            id=COURT, jurisdiction=Court.FEDERAL_DISTRICT, in_use=True
        )
        cls.bob = UserFactory()
        cls.jane = UserFactory()

    @staticmethod
    def _make_fq(user, status: int = PROCESSING_STATUS.ENQUEUED):
        """Create a docket fetch request for COURT."""
        return PacerFetchQueueFactory(
            user=user,
            request_type=REQUEST_TYPE.DOCKET,
            court_id=COURT,
            docket_number="1:20-cv-00001",
            status=status,
        )

    @staticmethod
    def _set_status(fq: PacerFetchQueue, status: int) -> None:
        """Change a request's status, as a fetch task would."""
        PacerFetchQueue.objects.filter(pk=fq.pk).update(status=status)


@override_settings(RECAP_FETCH_DEFAULT_COURT_RATE="1/s")
@mock.patch("cl.recap.fetch_scheduler.do_pacer_fetch")
class FetchDispatchTest(SchedulerDatabaseTestCase):
    """The daemon's cycle hands requests to Celery at each court's rate."""

    def test_court_waits_for_a_worker_to_start_its_request(
        self, mock_do_pacer_fetch: mock.MagicMock
    ) -> None:
        """The interval counts from the real start, read from PostgreSQL."""
        first, second = self._make_fq(self.bob), self._make_fq(self.bob)
        with time_machine.travel(NOON, tick=False) as traveller:
            schedule_fetch(first)
            schedule_fetch(second)

            self.assertEqual(run_dispatch_cycle(), 1)
            mock_do_pacer_fetch.assert_called_once_with(first)

            # Every worker is busy, so the first request is still ENQUEUED.
            traveller.shift(timedelta(minutes=1))
            self.assertEqual(run_dispatch_cycle(), 0)

            # A worker starts it. The cycle notices and starts the interval.
            self._set_status(first, PROCESSING_STATUS.IN_PROGRESS)
            self.assertEqual(run_dispatch_cycle(), 0)
            traveller.shift(timedelta(milliseconds=999))
            self.assertEqual(run_dispatch_cycle(), 0)

            traveller.shift(timedelta(milliseconds=1))
            self.assertEqual(run_dispatch_cycle(), 1)
            mock_do_pacer_fetch.assert_called_with(second)


@mock.patch("cl.recap.fetch_scheduler.send_recap_fetch_webhooks")
class FetchSweeperTest(SchedulerDatabaseTestCase):
    """No request stays ENQUEUED forever."""

    def test_fails_only_requests_stuck_in_enqueued(
        self, mock_webhooks: mock.MagicMock
    ) -> None:
        """Old ENQUEUED rows fail; recent, started or ancient rows don't."""
        with time_machine.travel(NOON - timedelta(days=30), tick=False):
            ancient = self._make_fq(self.bob)
        with time_machine.travel(NOON - timedelta(hours=2), tick=False):
            stale = self._make_fq(self.bob)
            schedule_fetch(stale)
            started = self._make_fq(
                self.jane, status=PROCESSING_STATUS.IN_PROGRESS
            )
        with time_machine.travel(NOON - timedelta(minutes=10), tick=False):
            recent = self._make_fq(self.jane)

        with time_machine.travel(NOON, tick=False):
            self.assertEqual(fail_stale_fetches(), 1)

        expected = [
            ("stuck for two hours", stale, PROCESSING_STATUS.FAILED),
            ("queued ten minutes ago", recent, PROCESSING_STATUS.ENQUEUED),
            ("already started", started, PROCESSING_STATUS.IN_PROGRESS),
            ("older than a day", ancient, PROCESSING_STATUS.ENQUEUED),
        ]
        for label, fq, status in expected:
            with self.subTest(label):
                fq.refresh_from_db()
                self.assertEqual(fq.status, status)

        self.assertEqual(stale.message, STALE_MESSAGE)
        mock_webhooks.assert_called_once()
        # The failed request is also gone from Redis, so it can't use a turn.
        self.assertIsNone(pop_next_fetch(COURT))


class FetchTaskGuardTest(SchedulerDatabaseTestCase):
    """A fetch task never runs a request that is already finished."""

    @mock.patch("cl.recap.tasks.is_pacer_court_accessible")
    def test_task_skips_a_request_failed_by_the_sweeper(
        self, mock_court_accessible: mock.MagicMock
    ) -> None:
        """The sweeper and a late Celery task can't both act on a request."""
        fq = self._make_fq(self.bob, status=PROCESSING_STATUS.FAILED)

        fetch_docket.apply(args=(fq.pk,))

        mock_court_accessible.assert_not_called()
        fq.refresh_from_db()
        self.assertEqual(fq.status, PROCESSING_STATUS.FAILED)


@override_settings(RECAP_FETCH_DEFAULT_COURT_RATE="1/s")
@mock.patch("cl.recap.api_serializers.get_or_cache_pacer_cookies")
@mock.patch("cl.recap.views.do_pacer_fetch")
class FetchApiSchedulingTest(SchedulerDatabaseTestCase):
    """The Fetch API queues requests and reports the estimated delay."""

    def setUp(self) -> None:
        """Log Jane in to the API."""
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.jane)
        self.url = reverse("pacerfetchqueue-list", kwargs={"version": "v4"})
        self.body = {
            "request_type": REQUEST_TYPE.DOCKET,
            "court": COURT,
            "docket_number": "1:20-cv-00001",
            "pacer_username": "jane",
            "pacer_password": "secret",
        }

    @override_switch(SCHEDULER_SWITCH, active=True)
    def test_queues_the_request_and_estimates_the_delay(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_cookies: mock.MagicMock,
    ) -> None:
        """With the switch on, the request waits and the wait is reported."""
        for _ in range(3):
            schedule_fetch(self._make_fq(self.bob))

        response = self.client.post(self.url, self.body, format="json")

        self.assertEqual(response.status_code, HTTPStatus.CREATED)
        data = response.json()
        self.assertEqual(data["estimated_execution_delay"], 1.0)
        self.assertIn("Estimated wait", data["message"])
        mock_do_pacer_fetch.assert_not_called()
        self.assertEqual(run_dispatch_cycle(), 1)

    @override_switch(SCHEDULER_SWITCH, active=False)
    def test_switch_off_keeps_the_old_behavior(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_cookies: mock.MagicMock,
    ) -> None:
        """With the switch off, requests go straight to Celery as before."""
        response = self.client.post(self.url, self.body, format="json")

        self.assertEqual(response.status_code, HTTPStatus.CREATED)
        self.assertIsNone(response.json()["estimated_execution_delay"])
        mock_do_pacer_fetch.assert_called_once()
        self.assertEqual(get_courts_with_waiting_fetches(), [])
