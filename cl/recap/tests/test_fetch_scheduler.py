import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from http import HTTPStatus
from io import StringIO
from unittest import mock

import time_machine
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from redis.exceptions import RedisError
from rest_framework.test import APIClient
from waffle.models import Flag
from waffle.testutils import override_flag

from cl.lib.redis_utils import get_redis_interface
from cl.recap import fetch_queue
from cl.recap.factories import PacerFetchQueueFactory
from cl.recap.fetch_queue import (
    daemon_is_alive,
    enqueue_fetch,
    estimate_delay,
    get_court_interval_ms,
    get_court_rates,
    get_courts_with_waiting_fetches,
    get_pending_fetches,
    get_queued_fetches,
    mark_fetch_started,
    pop_next_fetch,
    remove_fetch,
    set_court_rate,
    touch_daemon_heartbeat,
)
from cl.recap.fetch_scheduler import (
    HANDED_OFF_MESSAGE_PREFIX,
    LOST_MESSAGE,
    SCHEDULER_FLAG,
    SESSION_EXPIRED_MESSAGE,
    STALLED_MESSAGE,
    fail_stale_fetches,
    hand_off_fetch,
    run_dispatch_cycle,
    schedule_fetch,
)
from cl.recap.models import PROCESSING_STATUS, REQUEST_TYPE, PacerFetchQueue
from cl.recap.tasks import (
    fetch_docket,
    fetch_pacer_doc_by_rd,
    send_fq_webhooks,
)
from cl.search.factories import CourtFactory, RECAPDocumentFactory
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
        patcher = mock.patch.object(fetch_queue, "KEY_PREFIX", prefix)
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

    def test_rate_that_allows_no_requests_is_rejected(self) -> None:
        """A zero rate would stop the court and break its interval."""
        for rate in ("0/s", "-1/s", "1/0s"):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                set_court_rate(COURT, rate)
        self.assertEqual(get_court_rates(), {})

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

    def test_start_of_an_unqueued_request_changes_nothing(self) -> None:
        """Fetches that skipped the queue don't hold up or free a court."""
        enqueue_fetch(COURT, BOB, 1, T0)
        enqueue_fetch(COURT, BOB, 2, T0)
        self.assertEqual(pop_next_fetch(COURT, T0), 1)

        self.assertFalse(mark_fetch_started(COURT, 99, T0))

        self.assertEqual(get_pending_fetches([COURT]), {COURT: 1})
        self.assertIsNone(pop_next_fetch(COURT, T0 + 5000))
        self.assertTrue(mark_fetch_started(COURT, 1, T0 + 5000))
        self.assertIsNone(pop_next_fetch(COURT, T0 + 5999))
        self.assertEqual(pop_next_fetch(COURT, T0 + 6000), 2)


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

    def test_estimate_before_queueing_matches_the_one_after(self) -> None:
        """A request waiting on its commit gets the same estimate."""
        for fq_pk in (101, 102):
            enqueue_fetch(COURT, BOB, fq_pk, T0)
        enqueue_fetch(COURT, JANE, 201, T0)

        before = estimate_delay(COURT, JANE, T0, not_yet_queued=1)
        enqueue_fetch(COURT, JANE, 202, T0)

        self.assertEqual(before, estimate_delay(COURT, JANE, T0))


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
    def _make_fq(
        user: User, status: int = PROCESSING_STATUS.ENQUEUED
    ) -> PacerFetchQueue:
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

    def _schedule(self, fq: PacerFetchQueue) -> float | None:
        """Queue a request, running the callbacks its commit would run."""
        with self.captureOnCommitCallbacks(execute=True):
            return schedule_fetch(fq)


@override_settings(RECAP_FETCH_DEFAULT_COURT_RATE="1/s")
@mock.patch("cl.recap.fetch_scheduler.send_fq_webhooks")
@mock.patch("cl.recap.fetch_scheduler._has_pacer_session", return_value=True)
@mock.patch("cl.recap.fetch_scheduler.do_pacer_fetch")
class FetchDispatchTest(SchedulerDatabaseTestCase):
    """The daemon's cycle hands requests to Celery at each court's rate."""

    def test_court_waits_for_a_worker_to_start_its_request(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_has_session: mock.MagicMock,
        mock_webhooks: mock.MagicMock,
    ) -> None:
        """The interval counts from the real start, read from PostgreSQL."""
        first, second = self._make_fq(self.bob), self._make_fq(self.bob)
        with time_machine.travel(NOON, tick=False) as traveller:
            self._schedule(first)
            self._schedule(second)

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

    def test_expired_session_fails_without_using_the_turn(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_has_session: mock.MagicMock,
        mock_webhooks: mock.MagicMock,
    ) -> None:
        """Bob's dead request fails, and Jane's goes right after it."""
        bobs, janes = self._make_fq(self.bob), self._make_fq(self.jane)
        mock_has_session.side_effect = lambda user_id: user_id == self.jane.pk
        with time_machine.travel(NOON, tick=False) as traveller:
            # Users who join at the same instant are ordered by user ID, so
            # make sure Bob is first in line.
            self._schedule(bobs)
            traveller.shift(timedelta(milliseconds=1))
            self._schedule(janes)

            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(run_dispatch_cycle(), 0)
            self.assertEqual(run_dispatch_cycle(), 1)

        mock_do_pacer_fetch.assert_called_once_with(janes)
        bobs.refresh_from_db()
        self.assertEqual(bobs.status, PROCESSING_STATUS.FAILED)
        self.assertEqual(bobs.message, SESSION_EXPIRED_MESSAGE)
        mock_webhooks.delay.assert_called_once_with(bobs.pk)

    def test_request_joins_the_line_only_after_its_commit(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_has_session: mock.MagicMock,
        mock_webhooks: mock.MagicMock,
    ) -> None:
        """The daemon can't take a PK whose row isn't committed yet."""
        fq = self._make_fq(self.bob)

        with self.captureOnCommitCallbacks() as callbacks:
            delay = schedule_fetch(fq)
            self.assertEqual(get_courts_with_waiting_fetches(), [])
        for callback in callbacks:
            callback()

        self.assertEqual(delay, 0.0)
        self.assertEqual(get_courts_with_waiting_fetches(), [COURT])

    def test_handed_off_request_says_so(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_has_session: mock.MagicMock,
        mock_webhooks: mock.MagicMock,
    ) -> None:
        """The row records the hand-off before Celery can pick it up."""
        fq = self._make_fq(self.bob)
        self._schedule(fq)

        self.assertEqual(run_dispatch_cycle(), 1)

        fq.refresh_from_db()
        self.assertTrue(fq.message.startswith(HANDED_OFF_MESSAGE_PREFIX))

    def test_checks_every_handed_off_request_in_one_query(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_has_session: mock.MagicMock,
        mock_webhooks: mock.MagicMock,
    ) -> None:
        """The fallback costs one query per cycle, however many courts wait."""
        for fq_pk, court_id in enumerate((COURT, OTHER_COURT, "cand"), 1):
            enqueue_fetch(court_id, BOB, fq_pk)
            self.assertEqual(pop_next_fetch(court_id), fq_pk)

        with self.assertNumQueries(1):
            self.assertEqual(run_dispatch_cycle(), 0)


@mock.patch("cl.recap.fetch_scheduler.send_fq_webhooks")
@mock.patch("cl.recap.fetch_scheduler._has_pacer_session")
class FetchSweeperTest(SchedulerDatabaseTestCase):
    """No request stays ENQUEUED forever, and none that can still run fails."""

    def test_fails_only_queued_requests_that_cannot_succeed(
        self, mock_has_session: mock.MagicMock, mock_webhooks: mock.MagicMock
    ) -> None:
        """Expired sessions and lost requests fail; nothing else does."""
        # Bob keeps his PACER session alive; Jane's has expired.
        mock_has_session.side_effect = lambda user_id: user_id == self.bob.pk
        with time_machine.travel(NOON - timedelta(days=8), tick=False):
            ancient = self._make_fq(self.jane)
            self._schedule(ancient)
        with time_machine.travel(NOON - timedelta(hours=2), tick=False):
            still_in_line = self._make_fq(self.bob)
            self._schedule(still_in_line)
            lost = self._make_fq(self.bob)
            self._schedule(lost)
            expired = self._make_fq(self.jane)
            self._schedule(expired)
            # Rows from recap.email or pacer_bulk_fetch never went through
            # the queue.
            other_flow = self._make_fq(self.jane)
            started = self._make_fq(
                self.jane, status=PROCESSING_STATUS.IN_PROGRESS
            )
        with time_machine.travel(NOON - timedelta(minutes=10), tick=False):
            recent = self._make_fq(self.jane)
            self._schedule(recent)
        remove_fetch(COURT, self.bob.pk, lost.pk)

        with (
            time_machine.travel(NOON, tick=False),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.assertEqual(fail_stale_fetches(), 2)

        expected = [
            (
                "old but still in line",
                still_in_line,
                PROCESSING_STATUS.ENQUEUED,
            ),
            ("lost from Redis", lost, PROCESSING_STATUS.FAILED),
            ("session expired", expired, PROCESSING_STATUS.FAILED),
            ("not from the queue", other_flow, PROCESSING_STATUS.ENQUEUED),
            ("already started", started, PROCESSING_STATUS.IN_PROGRESS),
            ("queued ten minutes ago", recent, PROCESSING_STATUS.ENQUEUED),
            ("older than the lookback", ancient, PROCESSING_STATUS.ENQUEUED),
        ]
        for label, fq, status in expected:
            with self.subTest(label):
                fq.refresh_from_db()
                self.assertEqual(fq.status, status)

        self.assertEqual(lost.message, LOST_MESSAGE)
        self.assertEqual(expired.message, SESSION_EXPIRED_MESSAGE)
        self.assertCountEqual(
            [call.args for call in mock_webhooks.delay.call_args_list],
            [(lost.pk,), (expired.pk,)],
        )
        # The expired request is gone from Redis, so it can't use a turn.
        self.assertNotIn(expired.pk, get_queued_fetches(COURT, self.jane.pk))
        self.assertIn(still_in_line.pk, get_queued_fetches(COURT, self.bob.pk))

    @mock.patch("cl.recap.fetch_scheduler.do_pacer_fetch")
    def test_gives_handed_off_requests_time_to_finish(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_has_session: mock.MagicMock,
        mock_webhooks: mock.MagicMock,
    ) -> None:
        """A task that rolled back to retry keeps its request; a lost one not.

        PDF and attachment tasks run in a transaction, so a retry rolls the
        row back to ENQUEUED with no trace of the task in Redis.
        """
        mock_has_session.return_value = True
        with time_machine.travel(NOON - timedelta(hours=3), tick=False):
            lost, retrying = self._make_fq(self.bob), self._make_fq(self.jane)
            self._schedule(lost)
            self._schedule(retrying)
        with time_machine.travel(NOON - timedelta(hours=2), tick=False):
            self.assertTrue(hand_off_fetch(COURT, lost.pk))
        with time_machine.travel(NOON - timedelta(minutes=10), tick=False):
            self.assertTrue(hand_off_fetch(COURT, retrying.pk))

        with time_machine.travel(NOON, tick=False):
            self.assertEqual(fail_stale_fetches(), 1)

        lost.refresh_from_db()
        retrying.refresh_from_db()
        self.assertEqual(lost.status, PROCESSING_STATUS.FAILED)
        self.assertEqual(lost.message, STALLED_MESSAGE)
        self.assertEqual(retrying.status, PROCESSING_STATUS.ENQUEUED)

    def test_request_that_starts_during_the_sweep_is_left_alone(
        self, mock_has_session: mock.MagicMock, mock_webhooks: mock.MagicMock
    ) -> None:
        """The sweeper never fails a request on what it read before a change."""
        mock_has_session.return_value = True
        with time_machine.travel(NOON - timedelta(hours=2), tick=False):
            fq = self._make_fq(self.bob)
            self._schedule(fq)

        read_queue = get_queued_fetches

        def start_then_read(court_id: str, user_id: int) -> set[int]:
            """The daemon hands the request off and its task starts."""
            with mock.patch("cl.recap.fetch_scheduler.do_pacer_fetch"):
                self.assertEqual(pop_next_fetch(COURT), fq.pk)
                self.assertTrue(hand_off_fetch(COURT, fq.pk))
            self.assertTrue(mark_fetch_started(COURT, fq.pk))
            return read_queue(court_id, user_id)

        with (
            time_machine.travel(NOON, tick=False),
            mock.patch(
                "cl.recap.fetch_scheduler.get_queued_fetches",
                side_effect=start_then_read,
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.assertEqual(fail_stale_fetches(), 0)

        fq.refresh_from_db()
        self.assertEqual(fq.status, PROCESSING_STATUS.ENQUEUED)
        mock_webhooks.delay.assert_not_called()

    def test_sweeps_each_request_under_its_court_in_one_query(
        self, mock_has_session: mock.MagicMock, mock_webhooks: mock.MagicMock
    ) -> None:
        """A PDF request belongs to its docket's court, whatever fq.court is."""
        mock_has_session.return_value = True
        other_court = CourtFactory(
            id=OTHER_COURT, jurisdiction=Court.FEDERAL_BANKRUPTCY
        )
        rd = RECAPDocumentFactory(
            docket_entry__docket__court=Court.objects.get(pk=COURT)
        )
        with time_machine.travel(NOON - timedelta(hours=2), tick=False):
            for _ in range(3):
                self._schedule(self._make_fq(self.bob))
            pdf = PacerFetchQueueFactory(
                user=self.jane,
                request_type=REQUEST_TYPE.PDF,
                recap_document=rd,
                court=other_court,
            )
            self._schedule(pdf)
        self.assertEqual(get_queued_fetches(COURT, self.jane.pk), {pdf.pk})

        with time_machine.travel(NOON, tick=False), self.assertNumQueries(1):
            self.assertEqual(fail_stale_fetches(), 0)

        mock_has_session.side_effect = lambda user_id: user_id != self.jane.pk
        with time_machine.travel(NOON, tick=False):
            self.assertEqual(fail_stale_fetches(), 1)
        self.assertEqual(get_queued_fetches(COURT, self.jane.pk), set())


@mock.patch("cl.recap.fetch_scheduler.send_fq_webhooks")
class FetchSweeperLockTest(SchedulerDatabaseTestCase):
    """The sweeper never waits on a request that a running task holds."""

    def test_skips_requests_a_running_task_has_locked(
        self, mock_webhooks: mock.MagicMock
    ) -> None:
        """A PDF task's open transaction can't stall the daemon.

        The task holds the row's lock until it finishes, and its changes
        aren't committed yet, so the sweeper reads the row as a handed-off
        request that never started. The claim must skip a locked row rather
        than wait for it. Another connection can't see this test's rows, so
        the test checks the SQL instead of holding a real lock.
        """
        with time_machine.travel(NOON - timedelta(hours=2), tick=False):
            fq = PacerFetchQueueFactory(
                user=self.bob,
                request_type=REQUEST_TYPE.DOCKET,
                court_id=COURT,
                message=f"{HANDED_OFF_MESSAGE_PREFIX} {COURT}.",
            )

        with (
            time_machine.travel(NOON, tick=False),
            CaptureQueriesContext(connection) as queries,
        ):
            self.assertEqual(fail_stale_fetches(), 1)

        claims = [
            query["sql"]
            for query in queries.captured_queries
            if "FOR UPDATE" in query["sql"]
        ]
        self.assertEqual(len(claims), 1)
        self.assertIn("SKIP LOCKED", claims[0])
        fq.refresh_from_db()
        self.assertEqual(fq.status, PROCESSING_STATUS.FAILED)


@mock.patch(
    "cl.recap.tasks.send_recap_fetch_webhooks", new_callable=mock.AsyncMock
)
class FetchWebhookTaskTest(SchedulerDatabaseTestCase):
    """The daemon's webhooks are sent by Celery, not by the daemon."""

    def test_sends_the_webhooks_of_a_failed_request(
        self, mock_send: mock.AsyncMock
    ) -> None:
        """The task loads the request and sends its webhooks."""
        fq = self._make_fq(self.bob, status=PROCESSING_STATUS.FAILED)

        send_fq_webhooks.apply(args=(fq.pk,))

        mock_send.assert_awaited_once_with(fq)

    def test_does_nothing_for_a_deleted_request(
        self, mock_send: mock.AsyncMock
    ) -> None:
        """A request deleted before the task ran has nobody to tell."""
        fq = self._make_fq(self.bob, status=PROCESSING_STATUS.FAILED)
        fq_pk = fq.pk
        fq.delete()

        send_fq_webhooks.apply(args=(fq_pk,))

        mock_send.assert_not_awaited()


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


@mock.patch("cl.recap.tasks.is_pacer_court_accessible", return_value=True)
class FetchTaskStartTest(SchedulerDatabaseTestCase):
    """A fetch task frees its court as soon as it starts."""

    def _hand_off(self, fq: PacerFetchQueue) -> None:
        """Put a request in line and take it out, as the daemon would."""
        enqueue_fetch(COURT, fq.user_id, fq.pk)
        self.assertEqual(pop_next_fetch(COURT), fq.pk)

    @mock.patch(
        "cl.recap.tasks.get_pacer_cookie_from_cache",
        new_callable=mock.AsyncMock,
        return_value=None,
    )
    def test_docket_task_frees_its_court(
        self,
        mock_cookies: mock.AsyncMock,
        mock_court_accessible: mock.MagicMock,
    ) -> None:
        """The court is free once the task starts, whatever happens next."""
        fq = self._make_fq(self.bob)
        self._hand_off(fq)

        fetch_docket.apply(args=(fq.pk,))

        self.assertEqual(get_pending_fetches([COURT]), {})

    def test_pdf_task_frees_its_court_inside_its_transaction(
        self, mock_court_accessible: mock.MagicMock
    ) -> None:
        """PostgreSQL won't show the PDF task's status until it commits."""
        rd = RECAPDocumentFactory(
            docket_entry__docket__court=Court.objects.get(pk=COURT),
            is_available=True,
        )
        fq = PacerFetchQueueFactory(
            user=self.bob,
            request_type=REQUEST_TYPE.PDF,
            recap_document=rd,
        )
        self._hand_off(fq)

        fetch_pacer_doc_by_rd.apply(args=(rd.pk, fq.pk))

        self.assertEqual(get_pending_fetches([COURT]), {})


@override_settings(RECAP_FETCH_DEFAULT_COURT_RATE="1/s")
@mock.patch("cl.recap.api_serializers.get_or_cache_pacer_cookies")
@mock.patch("cl.recap.views.do_pacer_fetch")
class FetchApiSchedulingTest(SchedulerDatabaseTestCase):
    """The Fetch API queues requests and reports the estimated delay."""

    def setUp(self) -> None:
        """Log Jane in to the API and start the daemon's heartbeat."""
        super().setUp()
        # Keep the dispatch cycle away from the real fetch tasks and cookies.
        fetch_patcher = mock.patch("cl.recap.fetch_scheduler.do_pacer_fetch")
        fetch_patcher.start()
        self.addCleanup(fetch_patcher.stop)
        session_patcher = mock.patch(
            "cl.recap.fetch_scheduler._has_pacer_session", return_value=True
        )
        session_patcher.start()
        self.addCleanup(session_patcher.stop)
        touch_daemon_heartbeat()
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

    @override_settings(WAFFLE_CACHE_PREFIX="test_fetch_scheduler_flag_on")
    @override_flag(SCHEDULER_FLAG, active=True)
    def test_queues_the_request_and_estimates_the_delay(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_cookies: mock.MagicMock,
    ) -> None:
        """With the flag on, the request waits and the wait is reported."""
        for _ in range(3):
            self._schedule(self._make_fq(self.bob))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, self.body, format="json")

        self.assertEqual(response.status_code, HTTPStatus.CREATED)
        data = response.json()
        self.assertEqual(data["estimated_execution_delay"], 1.0)
        self.assertIn("Estimated wait", data["message"])
        mock_do_pacer_fetch.assert_not_called()
        self.assertEqual(run_dispatch_cycle(), 1)

    @override_settings(WAFFLE_CACHE_PREFIX="test_fetch_scheduler_flag_off")
    @override_flag(SCHEDULER_FLAG, active=False)
    def test_flag_off_keeps_the_old_behavior(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_cookies: mock.MagicMock,
    ) -> None:
        """With the flag off, requests go straight to Celery as before."""
        response = self.client.post(self.url, self.body, format="json")

        self.assertEqual(response.status_code, HTTPStatus.CREATED)
        self.assertIsNone(response.json()["estimated_execution_delay"])
        mock_do_pacer_fetch.assert_called_once()
        self.assertEqual(get_courts_with_waiting_fetches(), [])

    @override_settings(WAFFLE_CACHE_PREFIX="test_fetch_scheduler_no_daemon")
    @override_flag(SCHEDULER_FLAG, active=True)
    def test_requests_skip_the_queue_while_the_daemon_is_down(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_cookies: mock.MagicMock,
    ) -> None:
        """Nothing would hand a queued request off, so it goes to Celery."""
        get_redis_interface("CACHE").delete(fetch_queue._heartbeat_key())

        response = self.client.post(self.url, self.body, format="json")

        self.assertEqual(response.status_code, HTTPStatus.CREATED)
        self.assertIsNone(response.json()["estimated_execution_delay"])
        mock_do_pacer_fetch.assert_called_once()
        self.assertEqual(get_courts_with_waiting_fetches(), [])

    @override_settings(WAFFLE_CACHE_PREFIX="test_fetch_scheduler_redis_down")
    @override_flag(SCHEDULER_FLAG, active=True)
    def test_requests_skip_the_queue_when_redis_fails(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_cookies: mock.MagicMock,
    ) -> None:
        """A Redis error never leaves a saved request with nothing to run it."""
        for target in ("daemon_is_alive", "estimate_delay"):
            mock_do_pacer_fetch.reset_mock()
            with (
                self.subTest(target),
                mock.patch(
                    f"cl.recap.fetch_scheduler.{target}",
                    side_effect=RedisError("Redis is down"),
                ),
            ):
                response = self.client.post(self.url, self.body, format="json")

                self.assertEqual(response.status_code, HTTPStatus.CREATED)
                self.assertIsNone(response.json()["estimated_execution_delay"])
                mock_do_pacer_fetch.assert_called_once()

    @override_settings(WAFFLE_CACHE_PREFIX="test_fetch_scheduler_per_user")
    def test_flag_can_target_a_single_user(
        self,
        mock_do_pacer_fetch: mock.MagicMock,
        mock_cookies: mock.MagicMock,
    ) -> None:
        """Only the users the flag is on for go through the queue."""
        flag = Flag(name=SCHEDULER_FLAG, everyone=None)
        flag.save()
        flag.users.add(self.jane)
        bob_client = APIClient()
        bob_client.force_authenticate(self.bob)

        with self.captureOnCommitCallbacks(execute=True):
            jane_response = self.client.post(
                self.url, self.body, format="json"
            )
            bob_response = bob_client.post(self.url, self.body, format="json")

        self.assertIsNotNone(jane_response.json()["estimated_execution_delay"])
        self.assertIsNone(bob_response.json()["estimated_execution_delay"])
        mock_do_pacer_fetch.assert_called_once()
        self.assertEqual(
            mock_do_pacer_fetch.call_args.args[0].pk, bob_response.json()["id"]
        )


@override_settings(RECAP_FETCH_DEFAULT_COURT_RATE="1/s")
class FetchQueueCommandTest(SchedulerDatabaseTestCase):
    """People can see the queue and change rates without redis-cli."""

    @staticmethod
    def _run(*args: str) -> str:
        """Run recap_fetch_queue and return what it printed."""
        out = StringIO()
        call_command("recap_fetch_queue", *args, stdout=out)
        return out.getvalue()

    def test_status_shows_each_users_waiting_requests(self) -> None:
        """The status lists the depth per court and per user."""
        for fq_pk in (1, 2, 3):
            enqueue_fetch(COURT, self.bob.pk, fq_pk)
        enqueue_fetch(COURT, self.jane.pk, 4)
        self.assertEqual(pop_next_fetch(COURT), 1)

        output = self._run("--status")

        self.assertIn("Scheduler daemon: NOT running", output)
        self.assertIn(f"{COURT}: 3 waiting", output)
        self.assertIn("handed off and not started: 1", output)
        self.assertIn(f"user {self.bob.pk}: 2", output)
        self.assertIn(f"user {self.jane.pk}: 1", output)

    def test_set_and_clear_a_courts_rate(self) -> None:
        """A court's own rate applies until it is cleared."""
        self._run("--set-rate", COURT, "1/2s")
        self.assertEqual(get_court_interval_ms(COURT), 2000)
        self.assertIn(f"{COURT}: 1/2s", self._run("--status"))

        self._run("--clear-rate", COURT)
        self.assertEqual(get_court_interval_ms(COURT), 1000)

    def test_bad_input_is_rejected(self) -> None:
        """Typos in the court or the rate never reach Redis."""
        cases = [
            ("unknown court", ("--set-rate", "nope", "1/s")),
            ("unparsable rate", ("--set-rate", COURT, "fast")),
            ("zero rate", ("--set-rate", COURT, "0/s")),
            ("unknown court to clear", ("--clear-rate", "nope")),
        ]
        for label, args in cases:
            with self.subTest(label), self.assertRaises(CommandError):
                self._run(*args)
        self.assertEqual(get_court_rates(), {})


@override_settings(RECAP_FETCH_SCHEDULER_DAEMON_ENABLED=True)
@mock.patch(
    "cl.recap.management.commands.recap_fetch_scheduler_daemon.fail_stale_fetches",
    return_value=0,
)
@mock.patch(
    "cl.recap.management.commands.recap_fetch_scheduler_daemon.time.sleep"
)
@mock.patch(
    "cl.recap.management.commands.recap_fetch_scheduler_daemon.capture_exception"
)
@mock.patch(
    "cl.recap.management.commands.recap_fetch_scheduler_daemon.run_dispatch_cycle",
    side_effect=RedisError("Redis is down"),
)
class FetchSchedulerDaemonTest(SchedulerRedisTestCase):
    """The daemon survives outages without flooding Sentry."""

    def test_backs_off_and_reports_a_failure_streak_once(
        self,
        mock_dispatch: mock.MagicMock,
        mock_capture: mock.MagicMock,
        mock_sleep: mock.MagicMock,
        mock_sweep: mock.MagicMock,
    ) -> None:
        """Waits double after each failure and Sentry hears about it once."""
        call_command("recap_fetch_scheduler_daemon", testing_iterations=6)

        self.assertEqual(mock_dispatch.call_count, 6)
        mock_capture.assert_called_once()
        # The API must not queue requests for a daemon that can't send them.
        self.assertFalse(daemon_is_alive())
        self.assertEqual(
            [sleep.args[0] for sleep in mock_sleep.call_args_list],
            [1, 2, 4, 8, 16],
        )

    def test_recovers_its_pace_after_a_good_cycle(
        self,
        mock_dispatch: mock.MagicMock,
        mock_capture: mock.MagicMock,
        mock_sleep: mock.MagicMock,
        mock_sweep: mock.MagicMock,
    ) -> None:
        """One good cycle resets the wait and the next failure is reported."""
        mock_dispatch.side_effect = [RedisError(), 0, RedisError()]

        call_command("recap_fetch_scheduler_daemon", testing_iterations=3)

        self.assertEqual(mock_capture.call_count, 2)
        self.assertEqual(
            [sleep.args[0] for sleep in mock_sleep.call_args_list], [1, 0.5]
        )
        self.assertTrue(daemon_is_alive())

    @mock.patch(
        "cl.recap.management.commands.recap_fetch_scheduler_daemon.close_old_connections"
    )
    def test_drops_broken_database_connections_every_cycle(
        self,
        mock_close: mock.MagicMock,
        mock_dispatch: mock.MagicMock,
        mock_capture: mock.MagicMock,
        mock_sleep: mock.MagicMock,
        mock_sweep: mock.MagicMock,
    ) -> None:
        """A database restart can't leave every later cycle failing."""
        mock_dispatch.side_effect = None

        call_command("recap_fetch_scheduler_daemon", testing_iterations=3)

        self.assertEqual(mock_close.call_count, 3)
