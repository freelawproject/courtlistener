"""Property-based parity tests: Hypothesis-generated Texas docket
inputs run through both the legacy ``merge_texas_docket`` and the
new framework-based driver, asserting the resulting DB state is
byte-identical (modulo PKs and timestamps).

What this catches:

- Direct divergences between the two merger implementations — any
  output field, row count, or per-row identity that differs.
- Ordering instabilities in the new merger: running the same set of
  dockets in two different orders should produce the same end state
  (the legacy merger has the same property and we cross-check both).

How:

- Hypothesis-native strategies build realistic Juriscraper-shaped
  docket dicts. Court IDs and trial-court districts are sampled
  from a fixed pool so the matching ``Court`` rows can be created
  once in ``setUpTestData``.
- Each example runs each merger inside a savepoint, snapshots the
  DB, and rolls back. The two snapshots are compared via deep
  equality after PK/FK normalization.

Scope limits in this iteration:

- Court-of-Appeals dockets only (the more common SC and CCA shapes
  follow). No appellate ``transfer_from`` block yet; that's a
  separate matrix.
- Documents are present but downloads are mocked / suppressed on
  both sides so the comparison covers the row state, not the file
  state.
"""

from datetime import date
from unittest.mock import patch

from django.db import transaction
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase
from juriscraper.state.texas.common import CourtID, CourtType

from cl.corpus_importer.tasks import (
    merge_texas_docket as legacy_merge_texas_docket,
)
from cl.people_db.models import (
    Attorney,
    AttorneyOrganization,
    AttorneyOrganizationAssociation,
    Party,
    PartyType,
    Role,
)
from cl.scrapers.mergers.state.texas.driver import (
    merge_texas_docket as new_merge_texas_docket,
)
from cl.search.factories import CourtFactory
from cl.search.models import (
    CaseTransfer,
    Docket,
    OriginatingCourtInformation,
    TrialCourtData,
)
from cl.search.state.texas.models import TexasDocketEntry, TexasDocument


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------
#
# The text alphabet excludes control characters and surrogates so the
# generated values survive a Postgres round-trip. Lengths are kept
# modest to keep test runs fast.

_TEXT_ALPHABET = st.characters(
    blacklist_categories=("Cs", "Cc"),
    blacklist_characters="\x00",
)
_short_text = st.text(alphabet=_TEXT_ALPHABET, min_size=0, max_size=30)
_short_text_nonempty = st.text(
    alphabet=_TEXT_ALPHABET, min_size=1, max_size=30
)

# A small fixed date window keeps Hypothesis exploring distinct values
# without burning examples on edge-case dates that aren't useful here.
_filing_dates = st.dates(
    min_value=date(2020, 1, 1), max_value=date(2026, 1, 1)
)

# Pre-baked docket numbers: a small distinct set so the test
# exercises both "new docket" and "matched existing docket" code
# paths across examples, without runaway cardinality.
_docket_numbers = st.sampled_from(
    [f"01-25-{i:05d}-CV" for i in range(0, 50)]
)

_party_types = st.sampled_from(["Appellant", "Appellee", "Intervenor"])


@st.composite
def _texas_attachment_dict(draw):
    """A single TexasCaseDocument entry."""
    return {
        "document_url": draw(
            st.from_regex(
                r"https://example\.com/[a-z]{3,8}\.pdf", fullmatch=True
            )
        ),
        "media_id": str(draw(st.uuids())),
        "media_version_id": str(draw(st.uuids())),
        "description": draw(_short_text),
        "file_size_bytes": draw(st.integers(min_value=100, max_value=10**6)),
        "file_size_str": draw(_short_text),
    }


@st.composite
def _texas_case_event_dict(draw):
    """A single case event with 0-2 attachments."""
    return {
        "date": draw(_filing_dates),
        "type": draw(_short_text_nonempty),
        "disposition": draw(_short_text),
        "remarks": draw(_short_text),
        "attachments": draw(
            st.lists(_texas_attachment_dict(), min_size=0, max_size=2)
        ),
    }


@st.composite
def _texas_party_dict(draw):
    """A single party with 0-2 attorney representatives."""
    return {
        "name": draw(_short_text_nonempty),
        "type": draw(_party_types),
        "representatives": draw(
            st.lists(
                _short_text_nonempty,
                min_size=0,
                max_size=2,
                unique=True,
            )
        ),
    }


@st.composite
def _texas_originating_district_court_dict(draw):
    """Originating-court block from a known district court (so the
    legacy ``Court.objects.get(pk=...)`` lookup resolves)."""
    return {
        "name": draw(_short_text),
        "court_type": CourtType.DISTRICT.value,
        "case": draw(_short_text),
        "county": draw(_short_text),
        "judge": draw(_short_text),
        "reporter": draw(_short_text),
        "punishment": draw(_short_text),
        # district=5 maps to "texdistct6" via texas_originating_court_to_court_id;
        # we pre-create that Court in setUpTestData.
        "district": 5,
    }


@st.composite
def _texas_unknown_originating_court_dict(draw):
    """Originating-court block with UNKNOWN court_type → OCI / TCD /
    APPEAL transfer all short-circuit. Useful for exercising the
    "no lower court info" branch."""
    return {
        "name": draw(_short_text),
        "court_type": CourtType.UNKNOWN.value,
        "case": "",
        "county": draw(_short_text),
        "judge": draw(_short_text),
        "reporter": draw(_short_text),
        "punishment": draw(_short_text),
    }


@st.composite
def _texas_coa_docket_dict(draw):
    """A Court-of-Appeals docket dict.

    Restrictions for the first parity-test iteration:
    - Court fixed to the first court of appeals (``txctapp1``).
    - Originating court is either a known district or UNKNOWN.
    - No ``transfer_from`` workload/jurisdiction transfers.
    - Appellate briefs always empty (skip the brief-pairing matrix
      here; the brief logic is exercised separately in the unit
      tests).
    """
    # Case-event uniqueness: legacy's
    # ``merge_texas_docket_entry`` collapses two scraped events with
    # identical ``(date, type, appellate_brief)`` into a single DB
    # row (last write wins), then disambiguates re-scrapes via
    # ``sequence_number``. The new framework's
    # ``allow_duplicates=True`` mode preserves both as distinct rows.
    # That's a semantic improvement we can't strictly call parity on;
    # keep the strategy to (date, type) uniqueness so the parity
    # assertion focuses on realistic inputs.
    case_events = draw(
        st.lists(
            _texas_case_event_dict(),
            min_size=0,
            max_size=3,
            unique_by=lambda e: (e["date"], e["type"]),
        )
    )

    originating_court = draw(
        st.one_of(
            _texas_originating_district_court_dict(),
            _texas_unknown_originating_court_dict(),
        )
    )
    return {
        "court_id": CourtID.FIRST_COURT_OF_APPEALS.value,
        "court_type": CourtType.APPELLATE.value,
        "docket_number": draw(_docket_numbers),
        "case_name": draw(_short_text),
        "case_name_full": draw(_short_text),
        "date_filed": draw(_filing_dates),
        "case_type": draw(_short_text),
        # Unique-by (name, type) mirrors realistic scrapes: duplicate
        # party rows from the same docket don't happen in practice.
        # The legacy merger tolerates them via get-or-create; the new
        # framework treats duplicate NKs as an invariant violation.
        # Caller-side dedup is the natural fix for real divergence —
        # we restrict the strategy here to keep the parity assertion
        # focused on realistic input shapes.
        "parties": draw(
            st.lists(
                _texas_party_dict(),
                min_size=0,
                max_size=3,
                unique_by=lambda p: (p["name"], p["type"]),
            )
        ),
        "originating_court": originating_court,
        "case_events": case_events,
        "appellate_briefs": [],
        "transfer_from": None,
        "transfer_to": None,
    }


# ---------------------------------------------------------------------------
# DB snapshot helpers
# ---------------------------------------------------------------------------
#
# A snapshot is a hashable, comparison-friendly summary of the rows
# both mergers care about. PKs and timestamps are excluded; FKs are
# resolved to their natural identifiers (Court.id string, Party.name,
# etc.) so two runs that produce structurally-identical rows compare
# equal regardless of insert order or PK sequence position.


def _snapshot_db() -> dict:
    """Capture the parts of the DB the Texas merger writes to."""
    return {
        "dockets": sorted(
            (_snapshot_docket(d) for d in Docket.objects.all()),
            key=lambda d: (d["court_id"], d["docket_number_core"]),
        ),
        "parties": sorted(
            p.name for p in Party.objects.all() if p.name
        ),
        "attorneys": sorted(
            (a.name, a.contact_raw, a.email, a.phone, a.fax)
            for a in Attorney.objects.all()
        ),
        "attorney_orgs": sorted(
            (
                o.lookup_key,
                o.name,
                o.address1,
                o.address2,
                o.city,
                o.state,
                o.zip_code,
            )
            for o in AttorneyOrganization.objects.all()
        ),
        "case_transfers": sorted(
            _snapshot_case_transfer(t)
            for t in CaseTransfer.objects.all()
        ),
    }


def _snapshot_docket(d: Docket) -> dict:
    return {
        "court_id": d.court_id,
        "docket_number": d.docket_number,
        "docket_number_core": d.docket_number_core,
        "docket_number_raw": d.docket_number_raw,
        "case_name": d.case_name,
        "case_name_full": d.case_name_full,
        "date_filed": d.date_filed,
        "cause": d.cause,
        "source": d.source,
        "appeal_from_id": d.appeal_from_id,
        "appeal_from_str": d.appeal_from_str,
        "oci": _snapshot_oci(d.originating_court_information),
        "tcd": _snapshot_tcd(
            TrialCourtData.objects.filter(docket=d).first()
        ),
        "entries": sorted(
            (_snapshot_entry(e) for e in d.texasdocketentry_set.all()),
            key=lambda e: (
                e["date_filed"] or date.min,
                e["entry_type"],
                e["appellate_brief"],
                e["sequence_number"],
            ),
        ),
        "party_types": sorted(
            _snapshot_party_type(pt)
            for pt in PartyType.objects.filter(docket=d)
        ),
        "roles": sorted(
            _snapshot_role(r) for r in Role.objects.filter(docket=d)
        ),
        "org_associations": sorted(
            _snapshot_assoc(a)
            for a in AttorneyOrganizationAssociation.objects.filter(
                docket=d
            )
        ),
    }


def _snapshot_oci(oci: OriginatingCourtInformation | None) -> dict | None:
    if oci is None:
        return None
    return {
        "docket_number": oci.docket_number,
        "docket_number_raw": oci.docket_number_raw,
        "court_reporter": oci.court_reporter,
        "assigned_to_str": oci.assigned_to_str,
        "assigned_to_id": oci.assigned_to_id,
    }


def _snapshot_tcd(tcd: TrialCourtData | None) -> dict | None:
    if tcd is None:
        return None
    return {
        "docket_number_trial": tcd.docket_number_trial,
        "docket_number_raw_trial": tcd.docket_number_raw_trial,
        "judge_str": tcd.judge_str,
        "judge_id": tcd.judge_id,
        "reporter": tcd.reporter,
        "court_name": tcd.court_name,
        "court_id": tcd.court_id,
        "punishment": tcd.punishment,
        "county": tcd.county,
    }


def _snapshot_entry(e: TexasDocketEntry) -> dict:
    return {
        "date_filed": e.date_filed,
        "entry_type": e.entry_type,
        "appellate_brief": e.appellate_brief,
        "sequence_number": e.sequence_number,
        "description": e.description,
        "disposition": e.disposition,
        "remarks": e.remarks,
        "documents": sorted(
            (_snapshot_document(d) for d in e.texasdocument_set.all()),
            key=lambda d: d["media_id"],
        ),
    }


def _snapshot_document(d: TexasDocument) -> dict:
    return {
        "media_id": str(d.media_id),
        "media_version_id": str(d.media_version_id),
        "description": d.description,
        "url": d.url,
    }


def _snapshot_party_type(pt: PartyType) -> tuple:
    return (pt.party.name, pt.name, pt.date_terminated, pt.extra_info)


def _snapshot_role(r: Role) -> tuple:
    return (
        r.party.name,
        r.attorney.name,
        r.role,
        r.role_raw,
        r.date_action,
    )


def _snapshot_assoc(a: AttorneyOrganizationAssociation) -> tuple:
    return (a.attorney.name, a.attorney_organization.lookup_key)


def _snapshot_case_transfer(t: CaseTransfer) -> tuple:
    return (
        t.origin_court_id,
        t.origin_docket_number,
        t.destination_court_id,
        t.destination_docket_number,
        t.transfer_date,
        t.transfer_type,
        # Resolve docket FKs to their natural identifier so the
        # snapshot doesn't trip over insert-order-dependent PKs.
        _docket_natural_id(t.origin_docket),
        _docket_natural_id(t.destination_docket),
    )


def _docket_natural_id(d: Docket | None) -> tuple | None:
    if d is None:
        return None
    return (d.court_id, d.docket_number_core)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TexasMergerParityTest(HypothesisTestCase):
    """Property-based parity tests between the legacy
    ``cl.corpus_importer.tasks.merge_texas_docket`` and the new
    framework-based driver.

    Each Hypothesis example runs both mergers against a freshly-
    rolled-back baseline and compares the resulting DB state.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # Courts referenced by the COA strategy. Created once and
        # preserved across all Hypothesis examples in this class.
        cls.texas_coa1 = CourtFactory.create(id="txctapp1")
        cls.texas_district = CourtFactory.create(id="texdistct6")

    def setUp(self) -> None:
        # Suppress Celery dispatch on both sides so the comparison
        # focuses on row state, not on download side-effects.
        self._patches = [
            patch("cl.corpus_importer.tasks.download_texas_document.si"),
            patch(
                "cl.corpus_importer.tasks.extract_formatted_text_document.s"
            ),
            patch("cl.corpus_importer.tasks.download_document_in_stream"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()

    # ------------------------------------------------------------------
    # Isolated-run plumbing
    # ------------------------------------------------------------------

    def _run_isolated(self, fn) -> dict:
        """Run ``fn`` inside a savepoint, snapshot the DB, then roll
        back so the next isolated run starts from the same baseline.

        Wraps the snapshot in ``captureOnCommitCallbacks(execute=False)``
        so any ``transaction.on_commit`` calls the legacy merger
        registers are dropped (we don't want their side-effects in
        the parity comparison).
        """
        sid = transaction.savepoint()
        try:
            with self.captureOnCommitCallbacks(execute=False):
                fn()
            return _snapshot_db()
        finally:
            transaction.savepoint_rollback(sid)

    def _run_legacy(self, dockets: list[dict]) -> dict:
        return self._run_isolated(
            lambda: [
                legacy_merge_texas_docket(d, download_attachments=False)
                for d in dockets
            ]
        )

    def _run_new(self, dockets: list[dict]) -> dict:
        return self._run_isolated(
            lambda: [
                new_merge_texas_docket(d, download_attachments=False)
                for d in dockets
            ]
        )

    # ------------------------------------------------------------------
    # Property: legacy and new produce equivalent DB state
    # ------------------------------------------------------------------

    @given(
        dockets=st.lists(
            _texas_coa_docket_dict(),
            min_size=1,
            max_size=3,
            # Distinct docket_numbers per list so each Hypothesis
            # example exercises a batch of independent dockets. Same-
            # docket re-merges have semantically-meaningful legacy/new
            # divergences (legacy ``disassociate_extraneous_entities``
            # deletes missing parties; the new ``Union`` strategy is
            # additive) that deserve their own targeted tests rather
            # than tripping the property-based assertion.
            unique_by=lambda d: d["docket_number"],
        )
    )
    @settings(
        max_examples=75,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_parity_legacy_vs_new(self, dockets: list[dict]) -> None:
        """For any sequence of distinct COA dockets, merging through
        the legacy code and merging through the new driver produce
        byte-identical end-state databases."""
        legacy_snapshot = self._run_legacy(dockets)
        new_snapshot = self._run_new(dockets)
        self.assertEqual(legacy_snapshot, new_snapshot)

    # ------------------------------------------------------------------
    # Property: merge order doesn't change the end state
    # ------------------------------------------------------------------

    @given(
        dockets=st.lists(
            _texas_coa_docket_dict(),
            min_size=2,
            max_size=4,
            unique_by=lambda d: d["docket_number"],
        ),
        data=st.data(),
    )
    @settings(
        max_examples=75,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_new_merger_is_order_independent(
        self, dockets: list[dict], data
    ) -> None:
        """Merging a batch of distinct dockets through the new driver
        produces the same end-state DB regardless of order.

        ``data.draw`` picks a permutation of ``dockets`` so Hypothesis
        can shrink toward minimal counterexamples (e.g. a 2-docket
        swap) when an ordering bug exists.
        """
        permutation = data.draw(st.permutations(range(len(dockets))))
        reordered = [dockets[i] for i in permutation]
        forward_snapshot = self._run_new(dockets)
        reordered_snapshot = self._run_new(reordered)
        self.assertEqual(forward_snapshot, reordered_snapshot)

    @given(
        dockets=st.lists(
            _texas_coa_docket_dict(),
            min_size=2,
            max_size=4,
            unique_by=lambda d: d["docket_number"],
        ),
        data=st.data(),
    )
    @settings(
        max_examples=75,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_legacy_merger_is_order_independent(
        self, dockets: list[dict], data
    ) -> None:
        """Companion property check: the legacy merger has the same
        order invariance. If this ever fails we'd know we found a
        bug *in legacy* — which doesn't block migration but is worth
        knowing about."""
        permutation = data.draw(st.permutations(range(len(dockets))))
        reordered = [dockets[i] for i in permutation]
        forward_snapshot = self._run_legacy(dockets)
        reordered_snapshot = self._run_legacy(reordered)
        self.assertEqual(forward_snapshot, reordered_snapshot)
