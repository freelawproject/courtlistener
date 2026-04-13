import time

from django.conf import settings
from django.utils.timezone import localtime
from redis import ConnectionError as RedisConnectionError
from requests.exceptions import HTTPError, Timeout

from cl.corpus_importer.scotus_daemon_utils import (
    HIGHEST_KNOWN_HASH,
    SEQUENCE_BASE,
    SEQUENCES,
    current_scotus_term_year,
    format_docket_number,
    next_term_starts_probing,
    scotus_blocked_attempts_key,
    scotus_court_wait_key,
    scotus_empty_probe_attempts_key,
    scotus_highest_known_field,
)
from cl.corpus_importer.tasks import (
    fetch_scotus_docket_json,
    process_scotus_hit,
)
from cl.corpus_importer.utils import (
    compute_binary_probe_jitter,
    compute_blocked_court_wait,
    compute_next_binary_probe,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import get_redis_interface


def _handle_scotus_http_error(r, court_blocked_attempts: int) -> None:
    """Apply exponential backoff after HTTPError while probing SCOTUS."""
    if court_blocked_attempts > settings.SCOTUS_COURT_BLOCKED_MAX_ATTEMPTS:
        _, total_accumulated_time = compute_blocked_court_wait(
            court_blocked_attempts - 1
        )
        logger.error(
            "SCOTUS probing has been blocked for around %s hours.",
            total_accumulated_time / 3600,
        )
        r.set(scotus_blocked_attempts_key(), 0)
        r.set(
            scotus_court_wait_key(),
            settings.SCOTUS_COURT_BLOCKED_WAIT,
            ex=settings.SCOTUS_COURT_BLOCKED_WAIT,
        )
    else:
        next_blocked_wait, _ = compute_blocked_court_wait(
            court_blocked_attempts
        )
        r.set(
            scotus_court_wait_key(),
            next_blocked_wait,
            ex=next_blocked_wait,
        )
        logger.warning(
            "HTTPError while probing SCOTUS. Aborting for %s hours.",
            next_blocked_wait / 3600,
        )


def _probe_scotus_sequence(
    r,
    sequence: str,
    term_year_2digit: int,
    testing: bool,
) -> tuple[int, bool]:
    """Probe a single (sequence, term-year) pair forward, synchronously.

    For each direct hit the raw JSON is archived to S3 inline and ingestion
    is enqueued via Celery. After the forward probe locates the latest
    case, any serials the geometric probe skipped are backfilled inline
    (fetched + archived + ingestion enqueued) within this same daemon
    iteration.

    :return: ``(hits_count, blocked)``. When ``blocked`` is True the caller
        must abort the overall iteration (a ``scotus:court_wait`` TTL has
        been set).
    """
    field = scotus_highest_known_field(sequence, term_year_2digit)
    raw_highest = r.hget(HIGHEST_KNOWN_HASH, field)
    if raw_highest is None:
        # For the CURRENT term (never-seeded) we fail loudly upstream. For the
        # next-term rollover window, however, missing state is expected — we
        # seed it with the sequence base sentinel.
        highest_known = SEQUENCE_BASE[sequence]
    else:
        highest_known = int(raw_highest)

    jitter = compute_binary_probe_jitter(testing)
    probe_iteration = 1
    probe_offset = 0
    latest_match = 0
    found_match = False
    reports_data: list[tuple[str, str]] = []

    while probe_offset + jitter < settings.SCOTUS_PROBE_MAX_OFFSET:
        # ``compute_next_binary_probe`` returns (highest + offset + jitter,
        # offset + jitter). The first value is the serial to probe.
        candidate_serial, probe_offset = compute_next_binary_probe(
            highest_known, probe_iteration, jitter
        )
        probe_iteration += 1
        candidate = format_docket_number(term_year_2digit, candidate_serial)

        try:
            text, _ = fetch_scotus_docket_json(candidate)
        except HTTPError:
            court_blocked_attempts = r.incr(scotus_blocked_attempts_key())
            _handle_scotus_http_error(r, court_blocked_attempts)
            return len(reports_data), True
        except Timeout:
            logger.warning(
                "SCOTUS website timed out while probing %s. Aborting this sequence.",
                candidate,
            )
            break

        if text:
            reports_data.append((candidate, text))
            latest_match = candidate_serial
            found_match = True
            r.set(scotus_blocked_attempts_key(), 0)
            r.set(scotus_empty_probe_attempts_key(), 0)
        elif found_match:
            # Boundary found: first blank hit after a valid case.
            break

    if not reports_data:
        return 0, False

    # Store in S3 + enqueue ingestion for every serial we hit directly.
    for docket_number, content in reports_data:
        process_scotus_hit(docket_number, content)

    # Synchronously backfill serials skipped by the geometric probe. Each
    # fetch is spaced by ``SCOTUS_BACKFILL_REQUEST_DELAY`` to respect the rate
    # limit.

    probe_hit_serials = {dn for dn, _ in reports_data}
    backfill_serials = [
        serial
        for serial in range(highest_known + 1, latest_match)
        if format_docket_number(term_year_2digit, serial)
        not in probe_hit_serials
    ]
    if backfill_serials:
        logger.info(
            "SCOTUS backfill running for %s serials (%s-%s to %s-%s).",
            len(backfill_serials),
            term_year_2digit,
            backfill_serials[0],
            term_year_2digit,
            backfill_serials[-1],
        )

    for serial in backfill_serials:
        dn = format_docket_number(term_year_2digit, serial)
        try:
            text, _ = fetch_scotus_docket_json(dn)
        except HTTPError:
            court_blocked_attempts = r.incr(scotus_blocked_attempts_key())
            _handle_scotus_http_error(r, court_blocked_attempts)
            # Persist watermark progress before bailing so the next
            # iteration doesn't re-probe serials we already ingested.
            r.hset(HIGHEST_KNOWN_HASH, field, latest_match)
            return len(reports_data), True
        except Timeout:
            logger.warning(
                "SCOTUS website timed out during backfill of %s. Skipping.",
                dn,
            )
            if settings.SCOTUS_BACKFILL_REQUEST_DELAY:
                time.sleep(settings.SCOTUS_BACKFILL_REQUEST_DELAY)
            continue

        if text is None:
            # Real gap: no case exists at this serial. Log and continue.
            logger.warning("SCOTUS backfill: no case found for docket %s", dn)
        else:
            process_scotus_hit(dn, text)

        if settings.SCOTUS_BACKFILL_REQUEST_DELAY:
            time.sleep(settings.SCOTUS_BACKFILL_REQUEST_DELAY)

    r.hset(HIGHEST_KNOWN_HASH, field, latest_match)
    logger.info(
        "SCOTUS %s %s: advanced watermark %s -> %s (%s direct hits).",
        sequence,
        term_year_2digit,
        highest_known,
        latest_match,
        len(reports_data),
    )
    return len(reports_data), False


def run_scotus_probe_iteration(r, testing: bool) -> None:
    """Run one full forward-probe iteration across all active SCOTUS targets.

    Mirrors the design of ``probe_or_scrape_iquery_pages`` but targets a
    single court with two parallel docket-number sequences (low serial
    range YY-1.., high serial range YY-5001..) and optionally spans a
    term-year rollover window. Runs synchronously inside
    the daemon; Celery is only used to hand off ingestion once each JSON
    file has been archived to S3.
    """
    today = localtime().date()
    current_term = current_scotus_term_year(today)

    # Fail loudly if the CURRENT term's watermarks are not seeded. The
    # operator must HSET them before enabling the daemon.
    missing_fields = [
        scotus_highest_known_field(seq, current_term)
        for seq in SEQUENCES
        if r.hget(
            HIGHEST_KNOWN_HASH,
            scotus_highest_known_field(seq, current_term),
        )
        is None
    ]
    if missing_fields:
        logger.error(
            "SCOTUS probing aborted: missing Redis seeds for fields %s. "
            "Seed with: redis-cli HSET %s <field> <serial>.",
            missing_fields,
            HIGHEST_KNOWN_HASH,
        )
        return

    targets: list[tuple[str, int]] = [(seq, current_term) for seq in SEQUENCES]
    if next_term_starts_probing(today):
        next_term = (current_term + 1) % 100
        targets.extend((seq, next_term) for seq in SEQUENCES)

    total_hits = 0
    for sequence, term_year in targets:
        hits, blocked = _probe_scotus_sequence(r, sequence, term_year, testing)
        total_hits += hits
        if blocked:
            # A court_wait TTL has been set; stop probing everything.
            return

    if total_hits == 0:
        empty_attempts = r.incr(scotus_empty_probe_attempts_key())
        empty_hours = (empty_attempts * settings.SCOTUS_PROBE_WAIT) / 3600
        logger.info(
            "No SCOTUS cases found this iteration (empty streak: %.1f h).",
            empty_hours,
        )
        if empty_hours >= settings.SCOTUS_EMPTY_PROBES_LIMIT_HOURS:
            logger.error(
                "SCOTUS probe has found no new cases for ~%s hours. "
                "Manual intervention may be required.",
                settings.SCOTUS_EMPTY_PROBES_LIMIT_HOURS,
            )
            r.set(scotus_empty_probe_attempts_key(), 0)
            r.set(scotus_court_wait_key(), 3600, ex=3600)


class Command(VerboseCommand):
    help = """Run the SCOTUS JSON docket probing daemon.

The goal of this daemon is to discover and ingest new SCOTUS cases as they
are docketed at supremecourt.gov.

Each iteration performs a binary (geometric) forward probe over both the
low-range (YY-1..) and high-range (YY-5001..) docket-number sequences for
the current SCOTUS term, synchronously fetching JSON files and archiving
them to S3. Ingestion of each archived file is handed off to Celery via
``process_scotus_docket``. Gaps jumped over by the geometric probe are
backfilled inline in the same iteration. Starting on July 1 of each calendar
year it also probes the upcoming term (YY+1) to catch the rollover moment.

Before the daemon will do anything, the current term's highest-known serials
must be seeded in Redis, e.g.:

    redis-cli HSET scotus:highest_known_serial low:25 <latest_low_serial>
    redis-cli HSET scotus:highest_known_serial high:25 <latest_high_serial>

If the seeds are missing the daemon logs an ERROR and exits the iteration
without probing.
"""

    def add_arguments(self, parser):
        parser.add_argument(
            "--testing-iterations",
            type=int,
            default=0,
            required=False,
            help="The number of iterations to run in testing mode.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        testing_iterations = options["testing_iterations"]
        testing = bool(testing_iterations)
        iterations_completed = 0
        r = get_redis_interface("CACHE")

        while True and settings.SCOTUS_PROBE_DAEMON_ENABLED:
            wait_key = scotus_court_wait_key()
            if r.exists(wait_key):
                ttl = r.ttl(wait_key)
                logger.info(
                    "SCOTUS probe paused for %s hours; sleeping until "
                    "the block lifts.",
                    round(ttl / 3600, 2),
                )
                if not testing_iterations:
                    time.sleep(max(ttl, 1))
            else:
                try:
                    run_scotus_probe_iteration(r, testing)
                except RedisConnectionError:
                    logger.info(
                        "Failed to connect to redis. Waiting a bit and "
                        "retrying."
                    )
                    time.sleep(10)
                    continue
                if not testing_iterations:
                    time.sleep(settings.SCOTUS_PROBE_WAIT)

            if testing_iterations:
                iterations_completed += 1
                if iterations_completed >= testing_iterations:
                    break
