"""Property-based parity tests for SCOTUS: Hypothesis-generated
docket dicts run through both the legacy
``cl.corpus_importer.tasks.merge_scotus_docket`` and the new
framework-based driver, asserting that the resulting DB state is
byte-identical (modulo PKs and timestamps).

Two properties exercised:

- **Parity**: legacy and new produce the same end-state DB on every
  input.
- **Order invariance**: merging a batch of distinct dockets in
  different orders produces the same end-state. Both mergers are
  expected to satisfy this; we check both so a counterexample tells
  us *which* side has the ordering bug.

Scope in this iteration:

- Single-court (``scotus``). Lower-court ``appeal_from`` resolution
  exercises both the "court found" and "court not found" branches by
  sampling between a known full name and one that won't resolve.
- Docket entries are pinned to numbered entries (``document_number``
  set) so the legacy entry-matching logic and the framework's
  ``allow_duplicates=True`` pairing both key on the same field. The
  unnumbered-minute-entry case has semantically different matching
  rules (legacy: ``(description, date_filed)``; new: edit-cost
  pairing on the ``None`` collision bucket) that deserve their own
  targeted tests rather than tripping the property assertion.
- Distinct docket numbers per Hypothesis example — same-docket
  re-merge exposes a known legacy-vs-new divergence in party
  handling (legacy's ``disassociate_extraneous_entities`` deletes
  missing parties; the new ``Union`` strategy preserves them).
"""

from datetime import date
from unittest.mock import patch

from django.db import transaction
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from cl.corpus_importer.tasks import (
    merge_scotus_docket as legacy_merge_scotus_docket,
)
from cl.people_db.models import (
    Attorney,
    AttorneyOrganization,
    AttorneyOrganizationAssociation,
    Party,
    PartyType,
    Role,
)
from cl.scrapers.mergers.federal.scotus.driver import (
    merge_scotus_docket as new_merge_scotus_docket,
)
from cl.search.factories import CourtFactory
from cl.search.models import (
    Docket,
    OriginatingCourtInformation,
    SCOTUSDocketEntry,
    SCOTUSDocument,
    ScotusDocketMetadata,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_TEXT_ALPHABET = st.characters(
    blacklist_categories=("Cs", "Cc"),
    blacklist_characters="\x00",
)
_short_text = st.text(alphabet=_TEXT_ALPHABET, min_size=0, max_size=30)
_short_text_nonempty = st.text(
    alphabet=_TEXT_ALPHABET, min_size=1, max_size=30
)

_filing_dates = st.dates(
    min_value=date(2020, 1, 1), max_value=date(2026, 1, 1)
)

# Pre-baked docket numbers: distinct enough to cover variety, small
# enough to occasionally repeat across examples (exercising the
# matched-docket path within a single example would need a separate
# strategy — distinct docket numbers within a list keeps each example
# focused on independent dockets).
_docket_numbers = st.sampled_from(
    [f"{year}-{i:04d}" for year in (24, 25) for i in range(0, 25)]
)

_party_types = st.sampled_from(["Petitioner", "Respondent", "Other"])

# Lower-court strategy:
# - ``None`` exercises the no-lower-court branch.
# - The fixed CA2 full name exercises the "court found via courts-db"
#   branch (we pre-create the matching ``Court`` row in setUpTestData).
# - The garbage name exercises the "court not found" fallback where
#   ``appeal_from`` stays NULL but ``appeal_from_str`` is recorded.
_lower_court_names = st.one_of(
    st.none(),
    st.just("United States Court of Appeals for the Second Circuit"),
    st.just("Imaginary Tribunal of Nowhere"),
)


@st.composite
def _scotus_attachment(draw):
    return {
        "description": draw(_short_text),
        "document_url": draw(
            st.from_regex(
                r"https://example\.com/[a-z]{3,8}\.pdf", fullmatch=True
            )
        ),
        # Carried by the parent entry's document_number; populated by
        # ``enrich_scotus_attachments`` on the legacy side and inlined
        # in the new driver — both copies of the same value at runtime.
        "document_number": None,
    }


@st.composite
def _scotus_docket_entry(draw):
    """A numbered SCOTUS docket entry with 0-2 attachments.

    Pinned to numbered entries (``document_number != None``) so legacy
    and new align on entry-matching NK. Unnumbered entries have
    different matching rules between the two implementations and
    aren't covered here.
    """
    entry_number = draw(st.integers(min_value=1, max_value=10**6))
    attachments = draw(
        st.lists(_scotus_attachment(), min_size=0, max_size=2)
    )
    # Mirror legacy ``enrich_scotus_attachments``: each attachment
    # inherits the parent entry's document_number.
    for att in attachments:
        att["document_number"] = entry_number
    return {
        "date_filed": draw(_filing_dates),
        "document_number": entry_number,
        "description": draw(_short_text),
        "description_html": draw(_short_text),
        "attachments": attachments,
    }


@st.composite
def _scotus_attorney(draw):
    """A SCOTUS attorney dict. Address parts come straight from
    Hypothesis; the resulting contact string usually doesn't parse
    cleanly enough for ``normalize_attorney_contact`` to produce a
    non-empty ``atty_org_info``, which means most generated
    attorneys won't trigger ``AttorneyOrganization`` creation. That's
    fine for parity testing — both mergers see the same input and
    follow the same parsing path."""
    return {
        "name": draw(_short_text_nonempty),
        "is_counsel_of_record": draw(st.booleans()),
        "title": draw(st.one_of(st.none(), _short_text)),
        "phone": draw(st.one_of(st.none(), _short_text)),
        "address": draw(_short_text),
        "city": draw(st.one_of(st.none(), _short_text)),
        "state": draw(st.one_of(st.none(), _short_text)),
        "zip": draw(st.one_of(st.none(), _short_text)),
        "email": draw(
            st.one_of(
                st.none(),
                st.from_regex(r"[a-z]+@[a-z]+\.com", fullmatch=True),
            )
        ),
    }


@st.composite
def _scotus_party(draw):
    return {
        "name": draw(_short_text_nonempty),
        "type": draw(_party_types),
        "attorneys": draw(
            st.lists(
                _scotus_attorney(),
                min_size=0,
                max_size=2,
                unique_by=lambda a: a["name"],
            )
        ),
    }


@st.composite
def _scotus_docket_dict(draw):
    """A full Juriscraper SCOTUS docket-report dict."""
    # Same uniqueness restriction as Texas for case events: the new
    # framework's ``allow_duplicates=True`` mode and the legacy
    # entry-matching code agree on numbered entries with distinct
    # entry_numbers, so we restrict to that.
    docket_entries = draw(
        st.lists(
            _scotus_docket_entry(),
            min_size=0,
            max_size=3,
            unique_by=lambda e: e["document_number"],
        )
    )
    return {
        "docket_number": draw(_docket_numbers),
        "capital_case": draw(st.booleans()),
        "date_filed": draw(st.one_of(st.none(), _filing_dates)),
        "case_name": draw(_short_text),
        "links": draw(_short_text),
        "lower_court": draw(_lower_court_names),
        "lower_court_case_numbers_raw": draw(
            st.one_of(st.none(), _short_text)
        ),
        "lower_court_case_numbers": draw(
            st.one_of(
                st.none(), st.lists(_short_text_nonempty, max_size=2)
            )
        ),
        "lower_court_decision_date": draw(
            st.one_of(st.none(), _filing_dates)
        ),
        "lower_court_rehearing_denied_date": draw(
            st.one_of(st.none(), _filing_dates)
        ),
        "questions_presented": draw(
            st.one_of(
                st.none(),
                st.from_regex(
                    r"https://example\.com/[a-z]{3,8}\.pdf", fullmatch=True
                ),
            )
        ),
        "discretionary_court_decision": draw(
            st.one_of(st.none(), _filing_dates)
        ),
        "docket_entries": docket_entries,
        "parties": draw(
            st.lists(
                _scotus_party(),
                min_size=0,
                max_size=3,
                unique_by=lambda p: (p["name"], p["type"]),
            )
        ),
    }


# ---------------------------------------------------------------------------
# DB snapshot helpers
# ---------------------------------------------------------------------------


def _snapshot_db() -> dict:
    """Capture the parts of the DB the SCOTUS merger touches."""
    return {
        "dockets": sorted(
            (_snapshot_docket(d) for d in Docket.objects.all()),
            key=lambda d: (d["court_id"], d["docket_number"]),
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
    }


def _snapshot_docket(d: Docket) -> dict:
    return {
        "court_id": d.court_id,
        "docket_number": d.docket_number,
        "docket_number_raw": d.docket_number_raw,
        "case_name": d.case_name,
        "date_filed": d.date_filed,
        "source": d.source,
        "appeal_from_id": d.appeal_from_id,
        "appeal_from_str": d.appeal_from_str,
        "oci": _snapshot_oci(d.originating_court_information),
        "metadata": _snapshot_metadata(
            ScotusDocketMetadata.objects.filter(docket=d).first()
        ),
        "entries": sorted(
            (_snapshot_entry(e) for e in d.scotusdocketentry_set.all()),
            key=lambda e: (
                e["date_filed"] or date.min,
                e["entry_number"] or -1,
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
        "date_judgment": oci.date_judgment,
        "date_rehearing_denied": oci.date_rehearing_denied,
    }


def _snapshot_metadata(m: ScotusDocketMetadata | None) -> dict | None:
    if m is None:
        return None
    return {
        "capital_case": m.capital_case,
        "date_discretionary_court_decision": (
            m.date_discretionary_court_decision
        ),
        "linked_with": m.linked_with,
        "questions_presented_url": m.questions_presented_url,
    }


def _snapshot_entry(e: SCOTUSDocketEntry) -> dict:
    return {
        "date_filed": e.date_filed,
        "entry_number": e.entry_number,
        "description": e.description,
        "sequence_number": e.sequence_number,
        "documents": sorted(
            (_snapshot_document(d) for d in e.scotusdocument_set.all()),
            key=lambda d: (
                d["document_number"] or -1,
                d["attachment_number"] or -1,
            ),
        ),
    }


def _snapshot_document(d: SCOTUSDocument) -> dict:
    return {
        "document_number": d.document_number,
        "attachment_number": d.attachment_number,
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


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class ScotusMergerParityTest(HypothesisTestCase):
    """Property-based parity tests between the legacy
    ``merge_scotus_docket`` and the new framework-based driver.

    Each Hypothesis example runs both mergers in isolated savepoints
    against the same input and compares the resulting DB state.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create(id="scotus", jurisdiction="F")
        # Resolvable lower court — matches the
        # "United States Court of Appeals for the Second Circuit"
        # branch of the strategy so both mergers fill ``appeal_from``.
        cls.ca2 = CourtFactory.create(
            id="ca2",
            full_name=(
                "United States Court of Appeals for the Second Circuit"
            ),
            jurisdiction="A",
        )

    def setUp(self) -> None:
        # Mock the SCOTUS download chain on both sides so the
        # comparison covers row state, not file side-effects.
        self._patches = [
            patch("cl.corpus_importer.tasks.chain"),
            patch(
                "cl.corpus_importer.tasks.download_scotus_document_pdf"
            ),
            patch("cl.corpus_importer.tasks.extract_pdf_document"),
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
                legacy_merge_scotus_docket(d, download_file=False)
                for d in dockets
            ]
        )

    def _run_new(self, dockets: list[dict]) -> dict:
        return self._run_isolated(
            lambda: [
                new_merge_scotus_docket(d, download_file=False)
                for d in dockets
            ]
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @given(
        dockets=st.lists(
            _scotus_docket_dict(),
            min_size=1,
            max_size=3,
            unique_by=lambda d: d["docket_number"],
        )
    )
    @settings(
        max_examples=300,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_parity_legacy_vs_new(self, dockets: list[dict]) -> None:
        """For any batch of distinct SCOTUS dockets, the legacy and
        new mergers produce byte-identical end-state databases."""
        legacy_snapshot = self._run_legacy(dockets)
        new_snapshot = self._run_new(dockets)
        self.assertEqual(legacy_snapshot, new_snapshot)

    @given(
        dockets=st.lists(
            _scotus_docket_dict(),
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
        """Merge order through the new driver doesn't change the
        end-state DB."""
        permutation = data.draw(st.permutations(range(len(dockets))))
        reordered = [dockets[i] for i in permutation]
        forward_snapshot = self._run_new(dockets)
        reordered_snapshot = self._run_new(reordered)
        self.assertEqual(forward_snapshot, reordered_snapshot)

    @given(
        dockets=st.lists(
            _scotus_docket_dict(),
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
        """Companion property check on the legacy merger."""
        permutation = data.draw(st.permutations(range(len(dockets))))
        reordered = [dockets[i] for i in permutation]
        forward_snapshot = self._run_legacy(dockets)
        reordered_snapshot = self._run_legacy(reordered)
        self.assertEqual(forward_snapshot, reordered_snapshot)
