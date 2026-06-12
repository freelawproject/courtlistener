import time

from celery import chain
from django.conf import settings
from django.utils.timezone import localtime
from httpx import HTTPStatusError as HTTPError
from httpx import TimeoutException as Timeout
from juriscraper.scotus import SCOTUSDocketReport
from redis import ConnectionError as RedisConnectionError

from cl.corpus_importer.scotus_daemon_utils import (
    HIGHEST_SCOTUS_KNOWN_SERIAL,
    HIGHEST_SCOTUS_OBSERVED_SERIAL,
    SEQUENCE_BASE,
    SEQUENCES,
    current_scotus_term_year,
    fetch_scotus_docket_json,
    format_docket_number,
    previous_term_still_probing,
    save_scotus_raw_to_s3,
    scotus_blocked_attempts_key,
    scotus_court_wait_key,
    scotus_empty_probe_attempts_key,
    scotus_highest_known_field,
)
from cl.corpus_importer.tasks import process_scotus_docket
from cl.corpus_importer.utils import (
    compute_binary_probe_jitter,
    compute_blocked_court_wait,
    compute_next_binary_probe,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.redis_utils import get_redis_interface
from cl.scrapers.tasks import subscribe_to_scotus_updates


def process_scotus_hit(docket_number: str, content: str) -> None:
    """Store the raw JSON to S3, parse it, and enqueue ingestion.

    :param docket_number: The docket number
    :param content: The raw JSON
    :returns: None
    """
    logger.info("Processing SCOTUS hit for docket %s.", docket_number)
    save_scotus_raw_to_s3(
        f"responses/dockets/scotus/{docket_number}.json", content
    )
    parser = SCOTUSDocketReport()
    parser._parse_text(content)
    if not parser.data.get("docket_number"):
        logger.error(
            "SCOTUS parser produced no docket_number for %s", docket_number
        )
        return
    chain(
        process_scotus_docket.s(parser.data, download_file=True),
        subscribe_to_scotus_updates.s(),
    ).apply_async()


def _handle_scotus_http_error(r, court_blocked_attempts: int) -> None:
    """Apply exponential backoff after HTTPError while probing SCOTUS."""
    if court_blocked_attempts > settings.SCOTUS_COURT_BLOCKED_MAX_ATTEMPTS:  # type: ignore[misc]
        _, total_accumulated_time = compute_blocked_court_wait(
            court_blocked_attempts - 1,
            base_wait=settings.SCOTUS_COURT_BLOCKED_WAIT,  # type: ignore[misc]
        )
        logger.error(
            "SCOTUS probing has been blocked for around %s hours.",
            total_accumulated_time / 3600,
        )
        r.set(scotus_blocked_attempts_key(), 0)
        r.set(
            scotus_court_wait_key(),
            settings.SCOTUS_COURT_BLOCKED_WAIT,  # type: ignore[misc]
            ex=settings.SCOTUS_COURT_BLOCKED_WAIT,  # type: ignore[misc]
        )
    else:
        next_blocked_wait, _ = compute_blocked_court_wait(
            court_blocked_attempts,
            base_wait=settings.SCOTUS_COURT_BLOCKED_WAIT,  # type: ignore[misc]
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


def _ingest_serial_range(
    r,
    field: str,
    sequence: str,
    term_year_2digit: int,
    from_serial: int,
    to_serial: int,
    probe_cache: dict[str, str] | None = None,
) -> tuple[int, bool]:
    """Ingest all serials in the range (from_serial, to_serial] inclusive.

    Serials present in probe_cache are processed without an HTTP request.
    All others are fetched from supremecourt.gov with a rate-limiting delay
    between requests. HIGHEST_SCOTUS_KNOWN_SERIAL is advanced after each
    serial so a crash mid-loop leaves a safe resume point.

    :param r: Redis interface.
    :param field: Hash field (e.g. ``"low:25"``).
    :param sequence: Docket-number sequence.
    :param term_year_2digit: 2-digit SCOTUS term year.
    :param from_serial: Last serial already ingested (exclusive lower bound).
    :param to_serial: Highest observed serial (inclusive upper bound).
    :param probe_cache: Optional mapping of docket-number → JSON content for
        serials already fetched during the probe phase.
    :return: ``(hits_count, blocked)``.
    """
    if probe_cache is None:
        probe_cache = {}

    hits = 0

    for serial in range(from_serial + 1, to_serial + 1):
        dn = format_docket_number(term_year_2digit, serial, sequence)

        if dn in probe_cache:
            process_scotus_hit(dn, probe_cache[dn])
            hits += 1
        else:
            try:
                text, _ = fetch_scotus_docket_json(dn)
            except HTTPError:
                court_blocked_attempts = r.incr(scotus_blocked_attempts_key())
                _handle_scotus_http_error(r, court_blocked_attempts)
                return hits, True
            except Timeout:
                # Don't advance the watermark — leave it at the last
                # successfully ingested serial so the recovery path retries
                # this serial on the next probe iteration. A short pause lets
                # the site recover before we come back.
                logger.warning(
                    "SCOTUS website timed out during ingestion of %s. "
                    "Pausing for %s seconds before retrying.",
                    dn,
                    settings.SCOTUS_TIMEOUT_WAIT,  # type: ignore[misc]
                )
                r.set(
                    scotus_court_wait_key(),
                    settings.SCOTUS_TIMEOUT_WAIT,  # type: ignore[misc]
                    ex=settings.SCOTUS_TIMEOUT_WAIT,  # type: ignore[misc]
                )
                break

            if text:
                process_scotus_hit(dn, text)
                hits += 1
            else:
                logger.warning(
                    "SCOTUS ingestion: no case found for docket %s", dn
                )

            if settings.SCOTUS_BACKFILL_REQUEST_DELAY:  # type: ignore[misc]
                time.sleep(settings.SCOTUS_BACKFILL_REQUEST_DELAY)  # type: ignore[misc]

        r.hset(HIGHEST_SCOTUS_KNOWN_SERIAL, field, serial)

    logger.info(
        "SCOTUS %s %s: advanced watermark %s -> %s (%s hits).",
        sequence,
        term_year_2digit,
        from_serial,
        to_serial,
        hits,
    )
    return hits, False


def _probe_scotus_sequence(
    r,
    sequence: str,
    term_year_2digit: int,
    testing: bool,
) -> tuple[int, bool]:
    """Probe a single (sequence, term-year) pair forward, synchronously.

    Maintains two watermarks per (sequence, term):

    * ``HIGHEST_SCOTUS_KNOWN_SERIAL`` (highest ingested) — last serial whose
      S3-upload and Celery-enqueue completed.  Safe crash-recovery point.
    * ``HIGHEST_SCOTUS_OBSERVED_SERIAL`` (highest observed) — highest serial
      the probe confirmed exists on supremecourt.gov, written immediately on
      each hit so a crash between the probe phase and full ingestion can
      resume without re-probing.

    On entry, if ``observed > ingested`` (a previous run was interrupted
    mid-ingestion, or HIGHEST_SCOTUS_OBSERVED_SERIAL was seeded to backfill a
    known gap), the probe is skipped and the daemon sweeps the gap instead,
    ingesting at most ``SCOTUS_FIXED_SWEEP`` serials per iteration. Forward
    probing resumes once ``ingested`` catches up.

    :param r: Redis interface.
    :param sequence: The docket-number sequence.
    :param term_year_2digit: 2-digit SCOTUS term year.
    :param testing: When True jitter is disabled.
    :return: ``(hits_count, blocked)``. When ``blocked`` is True the caller
        must abort the overall iteration.
    """
    field = scotus_highest_known_field(sequence, term_year_2digit)

    raw_ingested = r.hget(HIGHEST_SCOTUS_KNOWN_SERIAL, field)
    if raw_ingested is None:
        # For the CURRENT term (never-seeded) we fail loudly upstream. For the
        # previous-term rollover window, however, missing state is expected seed
        # it with the sequence base sentinel.
        highest_ingested = SEQUENCE_BASE[sequence]
    else:
        highest_ingested = int(raw_ingested)

    raw_observed = r.hget(HIGHEST_SCOTUS_OBSERVED_SERIAL, field)
    highest_observed = (
        int(raw_observed) if raw_observed is not None else highest_ingested
    )

    # Recovery / sweep path: ``highest_observed > highest_ingested`` either
    # because a previous run was interrupted mid-ingestion, or because the
    # operator seeded ``HIGHEST_SCOTUS_OBSERVED_SERIAL`` ahead of the ingested
    # watermark to backfill a known gap. Resume ingestion without re-probing,
    # but cap each iteration at ``SCOTUS_FIXED_SWEEP`` serials so a large
    # backlog (thousands of cases) is processed slowly across many iterations
    # rather than hammering supremecourt.gov in one burst. The daemon falls
    # back to forward probing once ``highest_ingested`` catches up.
    if highest_observed > highest_ingested:
        sweep_cap = highest_ingested + settings.SCOTUS_FIXED_SWEEP  # type: ignore[misc]
        to_serial = min(highest_observed, sweep_cap)
        logger.info(
            "SCOTUS %s %s: %s ingestion (%s..%s] (highest observed: %s).",
            sequence,
            term_year_2digit,
            "sweeping" if to_serial < highest_observed else "resuming",
            highest_ingested,
            to_serial,
            highest_observed,
        )
        return _ingest_serial_range(
            r,
            field,
            sequence,
            term_year_2digit,
            from_serial=highest_ingested,
            to_serial=to_serial,
        )

    # Normal path: probe forward from the current watermark.
    max_probe = settings.SCOTUS_MAX_PROBE  # type: ignore[misc]
    jitter = compute_binary_probe_jitter(testing, max_probe=max_probe)
    probe_iteration = 1
    probe_offset = 0
    latest_match = 0
    found_match = False
    probe_cache: dict[str, str] = {}

    while True:
        candidate_serial, probe_offset = compute_next_binary_probe(
            highest_ingested, probe_iteration, jitter, max_probe=max_probe
        )
        probe_iteration += 1
        candidate = format_docket_number(
            term_year_2digit, candidate_serial, sequence
        )
        logger.info(
            "SCOTUS %s %s: probing candidate %s (offset %s).",
            sequence,
            term_year_2digit,
            candidate,
            probe_offset,
        )

        try:
            text, _ = fetch_scotus_docket_json(candidate)
        except HTTPError:
            court_blocked_attempts = r.incr(scotus_blocked_attempts_key())
            _handle_scotus_http_error(r, court_blocked_attempts)
            return 0, True
        except Timeout:
            logger.warning(
                "SCOTUS website timed out while probing %s. Aborting this sequence.",
                candidate,
            )
            break

        if text:
            logger.info(
                "SCOTUS %s %s: probe matched candidate %s.",
                sequence,
                term_year_2digit,
                candidate,
            )
            probe_cache[candidate] = text
            latest_match = candidate_serial
            found_match = True
            # Record the observation immediately so a crash after this point
            # can resume ingestion without re-probing.
            r.hset(HIGHEST_SCOTUS_OBSERVED_SERIAL, field, candidate_serial)
            r.set(scotus_blocked_attempts_key(), 0)
            r.set(scotus_empty_probe_attempts_key(), 0)
        elif found_match:
            # Boundary found: first blank hit after a valid case.
            break

        if probe_offset >= settings.SCOTUS_PROBE_MAX_OFFSET:  # type: ignore[misc]
            break

    if not probe_cache:
        return 0, False

    return _ingest_serial_range(
        r,
        field,
        sequence,
        term_year_2digit,
        from_serial=highest_ingested,
        to_serial=latest_match,
        probe_cache=probe_cache,
    )


def run_scotus_probe_iteration(r, testing: bool) -> None:
    """Run one full forward-probe iteration across all active SCOTUS targets.

    Targets SCOTUS with three parallel docket-number sequences (low serial
    range YY-1.., high serial range YY-5001.., and applications YYA1..)
    and optionally spans a term-year rollover window.
    """
    today = localtime().date()
    current_term = current_scotus_term_year(today)

    # Fail loudly if the CURRENT term's watermarks are not seeded.
    missing_fields = [
        scotus_highest_known_field(seq, current_term)
        for seq in SEQUENCES
        if r.hget(
            HIGHEST_SCOTUS_KNOWN_SERIAL,
            scotus_highest_known_field(seq, current_term),
        )
        is None
    ]
    if missing_fields:
        logger.error(
            "SCOTUS probing aborted: missing Redis seeds for fields %s. ",
            missing_fields,
        )
        return

    targets: list[tuple[str, int]] = [(seq, current_term) for seq in SEQUENCES]
    if previous_term_still_probing(today):
        prev_term = (current_term - 1) % 100
        targets.extend((seq, prev_term) for seq in SEQUENCES)

    total_hits = 0
    for sequence, term_year in targets:
        hits, blocked = _probe_scotus_sequence(r, sequence, term_year, testing)
        total_hits += hits
        if blocked:
            # A court_wait TTL has been set; stop probing everything.
            return

    if total_hits == 0:
        if today.weekday() in [5, 6]:
            # SCOTUS doesn't publish on weekends; don't count towards the
            # empty-probe streak to avoid spurious alerts.
            logger.info(
                "No SCOTUS cases found this iteration (weekend - not counting towards empty streak)."
            )
        else:
            empty_attempts = r.incr(scotus_empty_probe_attempts_key())
            empty_hours = (empty_attempts * settings.SCOTUS_PROBE_WAIT) / 3600  # type: ignore[misc]
            logger.info(
                "No SCOTUS cases found this iteration (empty streak: %.1f h).",
                empty_hours,
            )
            if empty_hours >= settings.SCOTUS_EMPTY_PROBES_LIMIT_HOURS:  # type: ignore[misc]
                logger.error(
                    "SCOTUS probe has found no new cases for ~%s hours. "
                    "Manual intervention may be required.",
                    settings.SCOTUS_EMPTY_PROBES_LIMIT_HOURS,  # type: ignore[misc]
                )
                r.set(scotus_empty_probe_attempts_key(), 0)
                r.set(scotus_court_wait_key(), 3600, ex=3600)


class Command(VerboseCommand):
    help = """Run the SCOTUS JSON docket probing daemon.

The goal of this daemon is to discover and ingest new SCOTUS cases as they
are docketed at supremecourt.gov.

Each iteration performs a binary (geometric) forward probe over three
docket-number sequences for the current SCOTUS term: low-range (YY-1..),
high-range (YY-5001..), and applications (YYA1..). It synchronously fetches
JSON files and archives them to S3. Ingestion of each archived file is
handed off to Celery via ``process_scotus_docket``. Gaps jumped over by the
geometric probe are backfilled inline in the same iteration. During July
it also probes the outgoing (previous) term to catch late filings.

When ``HIGHEST_SCOTUS_OBSERVED_SERIAL`` is ahead of
``HIGHEST_SCOTUS_KNOWN_SERIAL`` (e.g. an operator seeded the observed
watermark to onboard a backlog), the daemon switches to sweep mode for that
(sequence, term) pair: it ingests at most ``SCOTUS_FIXED_SWEEP`` serials per
iteration and skips probing until the ingested watermark catches up.

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

        while settings.SCOTUS_PROBE_DAEMON_ENABLED:  # type: ignore[misc]
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
                    time.sleep(settings.SCOTUS_PROBE_WAIT)  # type: ignore[misc]

            if testing_iterations:
                iterations_completed += 1
                if iterations_completed >= testing_iterations:
                    break
