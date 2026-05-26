"""Targeted tests for framework-internal branches that the broader
suite happens not to exercise.

These were identified by running ``coverage.py`` against the merger
package after the parity/property work landed. Each test here covers
a real branch in the framework (a documented behavior or an error
path) — they're not just chasing 100% by exercising defensively-coded
dead ends.

What we deliberately skip:

- Unreachable defensive guards (``model is None`` after schema
  validation passes, ``scrape is None and db is None`` in
  ``_reconcile_node``, ``cls is None`` in
  ``_materialize_pre_children``, etc.). These exist for robustness
  but can't be hit through the public API; faking them in tests
  would add noise without buying confidence.
- Helper internals that are exercised transitively by every existing
  Texas/SCOTUS test (PreResolvedRef detection, single-child FK
  injection, etc.). Coverage shows them as "missed" only because
  ``coverage.py`` reports branch coverage independently of statement
  coverage in some configurations.
"""

from datetime import date
from typing import Annotated

from cl.scrapers.mergers import (
    Aggregate,
    BridgeNode,
    DBWins,
    ErrorIfMissing,
    ExternalNodeRef,
    NoopIfMissing,
    PreResolvedRef,
    ScrapeWins,
    Union,
    apply,
    build_paired_tree,
    parent,
    reconcile,
)
from cl.scrapers.mergers.fields import extract_fields
from cl.scrapers.mergers.follow_up import FollowUp
from cl.scrapers.mergers.nk import OwnScalar
from cl.scrapers.mergers.paired import (
    _nk_elements_for_lookup,
    _scrape_ref_identity,
    _sibling_identity,
)
from cl.scrapers.mergers.prefetch import prefetch_root
from cl.scrapers.mergers.reconcile import pair_by_nk_allowing_duplicates
from cl.scrapers.mergers.refs import parent as parent_ref
from cl.scrapers.mergers.tests.testmodels.models import (
    TCounsel,
    TCourt,
    TDocket,
    TDocketEntry,
    TParty,
)
from cl.tests.cases import SimpleTestCase, TransactionTestCase


# ---------------------------------------------------------------------------
# fields.py: ``list[primitive]`` is treated as a scalar field
# ---------------------------------------------------------------------------


class ListOfPrimitivesIsScalarTest(SimpleTestCase):
    """A ``list[str]`` (or any non-Node element type) doesn't become a
    ``ChildListField``; it falls through to the ScalarField branch so
    Pydantic stores the list verbatim and the framework treats the
    whole field as scalar."""

    def test_list_of_primitives_classified_as_scalar(self) -> None:
        class _ListyDocket(Aggregate[TDocket]):
            natural_key = ("court", "docket_number_core")

            court: PreResolvedRef[TCourt]
            docket_number_core: str
            # A list of primitive strings — not Nodes. The framework
            # treats this as a scalar (passes through to Pydantic
            # storage).
            tags: list[str] = []

        # The ``tags`` field shows up as a ScalarField, not a
        # ChildListField. extract_fields() distinguishes by checking
        # whether the inner is a Node subclass.
        from cl.scrapers.mergers.fields import ChildListField, ScalarField

        descriptors = {f.name: f for f in extract_fields(_ListyDocket)}
        self.assertIn("tags", descriptors)
        self.assertIsInstance(descriptors["tags"], ScalarField)
        self.assertNotIsInstance(descriptors["tags"], ChildListField)


# ---------------------------------------------------------------------------
# fields.py: multiple collection strategies on one field raise TypeError
# ---------------------------------------------------------------------------


class MultipleCollectionStrategiesErrorTest(SimpleTestCase):
    """Declaring two collection strategies on the same field is a
    schema bug — the framework raises ``TypeError`` rather than
    silently picking one."""

    def test_two_collection_strategies_raises(self) -> None:
        from cl.scrapers.mergers.nodes import InternalNode

        class _Entry(InternalNode[TDocketEntry]):
            natural_key = (parent.docket, "entry_type")
            entry_type: str

        with self.assertRaises(TypeError) as ctx:

            class _BadDocket(Aggregate[TDocket]):
                natural_key = ("court", "docket_number_core")

                court: PreResolvedRef[TCourt]
                docket_number_core: str
                # Two collection strategies on one field — should fail.
                entries: Annotated[list[_Entry], Union, Union] = []

        self.assertIn("Multiple collection strategies", str(ctx.exception))


# ---------------------------------------------------------------------------
# nodes.py: BridgeNode init_subclass kwargs
# ---------------------------------------------------------------------------


class BridgeNodeInitSubclassKwargsTest(SimpleTestCase):
    """``BridgeNode.__init_subclass__`` only stamps the class with
    overrides when the corresponding kwarg is supplied. Cover both
    "with kwarg" and "without kwarg" (defaults preserved) paths."""

    def test_allow_duplicates_kwarg_overrides_default(self) -> None:
        class _AllowDupBridge(
            BridgeNode[TCounsel], allow_duplicates=True
        ):
            natural_key = ("party",)
            party: PreResolvedRef[TParty]

        self.assertTrue(_AllowDupBridge._mergers_allow_duplicates)

    def test_absence_policy_kwarg_overrides_default(self) -> None:
        class _ErrorBridge(
            BridgeNode[TCounsel], absence_policy=ErrorIfMissing
        ):
            natural_key = ("party",)
            party: PreResolvedRef[TParty]

        self.assertIs(
            _ErrorBridge._mergers_absence_policy, ErrorIfMissing
        )

    def test_defaults_preserved_without_kwargs(self) -> None:
        class _DefaultBridge(BridgeNode[TCounsel]):
            natural_key = ("party",)
            party: PreResolvedRef[TParty]

        # Defaults from BridgeNode's ClassVars.
        self.assertFalse(_DefaultBridge._mergers_allow_duplicates)


# ---------------------------------------------------------------------------
# nodes.py: ExternalNodeRef path_scoped kwarg
# ---------------------------------------------------------------------------


class ExternalNodeRefPathScopedKwargTest(SimpleTestCase):
    def test_path_scoped_false_kwarg_overrides_default(self) -> None:
        class _GlobalRef(ExternalNodeRef[TParty], path_scoped=False):
            natural_key = ("name",)
            name: str

        self.assertFalse(_GlobalRef._mergers_path_scoped)


# ---------------------------------------------------------------------------
# refs.py: PathRef equality with non-PathRef returns NotImplemented
# ---------------------------------------------------------------------------


class PathRefEqualityFallbackTest(SimpleTestCase):
    """``PathRef.__eq__`` should return ``NotImplemented`` (not
    ``False``) when compared to a non-``PathRef`` so Python's
    fallback comparison machinery can try the reflected operand."""

    def test_eq_with_non_pathref_returns_notimplemented(self) -> None:
        p = parent_ref.docket
        # Calling ``__eq__`` directly so we see ``NotImplemented``
        # (the high-level ``==`` operator hides it as ``False``).
        self.assertIs(p.__eq__("not a pathref"), NotImplemented)
        # And the public ``==`` falls through to False as expected.
        self.assertNotEqual(p, "not a pathref")


# ---------------------------------------------------------------------------
# reconcile.py: empty inputs to pair_by_nk_allowing_duplicates
# ---------------------------------------------------------------------------


class AllowDuplicatesEmptyInputsTest(SimpleTestCase):
    """``pair_by_nk_allowing_duplicates`` handles empty inputs
    cleanly without invoking the bipartite-assignment inner loop.

    The empty-bucket short-circuits in
    ``pair_by_nk_allowing_duplicates`` (where one side's bucket for a
    given NK is empty) keep ``_min_cost_assignment`` from being
    called at all in those cases."""

    def test_both_empty(self) -> None:
        result = pair_by_nk_allowing_duplicates(
            [], [], lambda x: x, lambda s, d: 0
        )
        self.assertEqual(result.pairs, [])
        self.assertEqual(result.scrape_only, [])
        self.assertEqual(result.db_only, [])

    def test_only_scrape_side(self) -> None:
        result = pair_by_nk_allowing_duplicates(
            ["a"], [], lambda x: x, lambda s, d: 0
        )
        self.assertEqual(result.pairs, [])
        self.assertEqual(result.scrape_only, ["a"])
        self.assertEqual(result.db_only, [])

    def test_only_db_side(self) -> None:
        result = pair_by_nk_allowing_duplicates(
            [], ["a"], lambda x: x, lambda s, d: 0
        )
        self.assertEqual(result.pairs, [])
        self.assertEqual(result.scrape_only, [])
        self.assertEqual(result.db_only, ["a"])


# ---------------------------------------------------------------------------
# prefetch.py: schema without a bound Django model
# ---------------------------------------------------------------------------


class PrefetchRequiresBoundModelTest(SimpleTestCase):
    """``prefetch_root`` raises a clear error when the schema class
    doesn't resolve to a Django model — a configuration bug worth
    surfacing loudly rather than crashing further downstream."""

    def test_unbound_schema_raises_clear_error(self) -> None:
        # Construct an Aggregate subclass that doesn't bind ModelT —
        # only abstract subclasses look like this, so the error path
        # is for users who forget to parameterize.
        class _Unbound(Aggregate):  # type: ignore[type-arg]
            pass

        with self.assertRaises(ValueError) as ctx:
            prefetch_root(_Unbound.model_construct(), prefetch_paths=None)
        self.assertIn("no bound Django model", str(ctx.exception))


# ---------------------------------------------------------------------------
# paired.py: _nk_elements_for_lookup rejects unsupported NK elements
# ---------------------------------------------------------------------------


class NkElementsForLookupRejectsUnsupportedTest(TransactionTestCase):
    """The helper accepts ``OwnScalar`` + preresolved ``SiblingRef``
    only. A ExternalNodeRef child in the NK is unsupported and raises
    ``NotImplementedError``.

    Uses ``TransactionTestCase`` because declaring the ExternalNodeRef
    triggers schema validation, which inspects related schemas — the
    error happens at lookup time, not at declaration time, so we
    have to actually invoke the helper."""

    databases = {"mergers_test"}

    def test_ExternalNodeRef_in_nk_raises(self) -> None:
        class _PartyRef(ExternalNodeRef[TParty]):
            natural_key = ("name",)
            name: str

        class _PartyTypeLookup(ExternalNodeRef[TParty]):
            # NK references ``party`` which is a ExternalNodeRef sibling —
            # not supported in the global/path-scoped lookup helper.
            natural_key = ("party",)
            party: _PartyRef
            name: str = ""

        with self.assertRaises(NotImplementedError) as ctx:
            _nk_elements_for_lookup(_PartyTypeLookup)
        self.assertIn("supported in this lookup code path", str(ctx.exception))


# ---------------------------------------------------------------------------
# paired.py: _sibling_identity handles None scrape ref
# ---------------------------------------------------------------------------


class SiblingIdentityNoneRefTest(SimpleTestCase):
    """A scrape ``Node`` whose sibling-ref field is ``None`` (e.g. a
    nullable PreResolvedRef) yields ``None`` as the identity component
    so the pair-by-NK key can still be constructed."""

    def test_returns_none_for_none_ref(self) -> None:
        class _Schema(Aggregate[TDocket]):
            natural_key = ("court", "docket_number_core")
            court: PreResolvedRef[TCourt]
            docket_number_core: str
            optional_court: PreResolvedRef[TCourt] | None = None

        court = TCourt(id="scotus", name="Supreme Court")
        instance = _Schema(
            court=court,
            docket_number_core="22-100",
            optional_court=None,
        )
        # ``optional_court`` is ``None`` on the instance → identity
        # extraction returns ``None``.
        self.assertIsNone(
            _sibling_identity(instance, "optional_court", resolved={})
        )


# ---------------------------------------------------------------------------
# paired.py: _scrape_ref_identity covers SiblingRef NK elements
# ---------------------------------------------------------------------------


class ScrapeRefIdentitySiblingRefTest(SimpleTestCase):
    """``_scrape_ref_identity`` is used for unresolved scrape ExternalNodeRefs
    as a hashable stand-in for their PK. When the ExternalNodeRef's NK
    includes a ``SiblingRef`` (a nested ref of its own), the identity
    has to recursively extract that sibling's identity. Cover the
    SiblingRef arm of the loop."""

    def test_identity_includes_sibling_ref_value(self) -> None:
        class _InnerRef(ExternalNodeRef[TParty]):
            natural_key = ("name",)
            name: str

        class _OuterRef(ExternalNodeRef[TParty]):
            # Self-referential-shaped NK exercising the SiblingRef
            # arm — the actual TParty model doesn't matter here; we
            # only check the helper's behavior.
            natural_key = ("name", "inner")
            name: str
            inner: _InnerRef | None = None

        inner = _InnerRef(name="A")
        outer = _OuterRef(name="B", inner=inner)
        identity = _scrape_ref_identity(outer)

        # First component is the sentinel; second is the OwnScalar
        # "B"; third is the sibling's identity (a nested tuple).
        self.assertEqual(identity[0], "__unresolved__")
        self.assertEqual(identity[1], "B")
        # The sibling's identity is itself an unresolved tuple
        # (resolved dict is empty in ``_scrape_ref_identity``).
        self.assertIsInstance(identity[2], tuple)
        self.assertEqual(identity[2][0], "__unresolved__")
        self.assertEqual(identity[2][1], "A")


# ---------------------------------------------------------------------------
# apply.py: ExternalNodeRef on_update returning follow-ups (matched + create)
# ---------------------------------------------------------------------------


class ExternalNodeRefOnUpdateFollowUpsTest(TransactionTestCase):
    """A ExternalNodeRef class that overrides ``on_update`` to return a
    list of ``FollowUp`` instances — both for the matched-with-update
    path and the CreateIfMissing path — must have its follow-ups
    propagated into ``outcome.follow_ups``."""

    databases = {"mergers_test"}

    def setUp(self) -> None:
        self.court = TCourt.objects.create(id="scotus", name="Supreme Court")
        self.docket = TDocket.objects.create(
            court=self.court, docket_number_core="22-100"
        )

    def test_create_path_propagates_follow_up(self) -> None:
        """CreateIfMissing path: scrape ref doesn't match → row
        inserted → ``on_update(None, new_db)`` fires → returned
        follow-up shows up in ``outcome.follow_ups``."""

        class _NoisyPartyRef(ExternalNodeRef[TParty]):
            natural_key = ("name",)
            name: str

            def on_update(self, old_db, new_db):
                if old_db is None and new_db is not None:
                    return [
                        FollowUp(
                            name="party-created",
                            fn=lambda pk: None,
                            args=(new_db.pk,),
                        )
                    ]
                return None

        from cl.scrapers.mergers.nodes import InternalNode

        class _PartyTypeSchema(InternalNode):
            # Bound model picked up via the generic param on the
            # bound _NoisyPartyRef. We just need a schema that
            # references the ExternalNodeRef via a ChildField so the
            # pre-materialization path runs.
            pass

        class _DocketSchema(Aggregate[TDocket]):
            natural_key = ("court", "docket_number_core")
            court: PreResolvedRef[TCourt]
            docket_number_core: str
            party_types: list["_PartyTypeFull"] = []

        from cl.people_db.models import (  # noqa: F401 (unused intentionally)
            Party as _RealParty,
        )
        from cl.scrapers.mergers.tests.testmodels.models import TPartyType

        class _PartyTypeFull(InternalNode[TPartyType]):
            natural_key = (parent.docket, "party", "role")
            party: _NoisyPartyRef
            role: str

        scrape = _DocketSchema(
            court=self.court,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeFull(
                    party=_NoisyPartyRef(name="New Person"),
                    role="Defendant",
                )
            ],
        )
        outcome = apply(reconcile(build_paired_tree(scrape)))

        names = [getattr(fu, "name", "") for fu in outcome.follow_ups]
        self.assertIn("party-created", names)

    def test_matched_path_field_update_fires_follow_up(self) -> None:
        """Matched ExternalNodeRef with an explicit ``ScrapeWins`` override
        on a non-NK field; on update the row gets written and
        ``on_update(old_db, new_db)`` fires with a follow-up."""

        # Pre-create the party so resolution finds it.
        existing_party = TParty.objects.create(
            name="Existing", description="stale"
        )
        from cl.scrapers.mergers.tests.testmodels.models import TPartyType

        TPartyType.objects.create(
            docket=self.docket, party=existing_party, role="Witness"
        )

        from cl.scrapers.mergers.nodes import InternalNode

        class _NoisyPartyRef(ExternalNodeRef[TParty]):
            natural_key = ("name",)
            name: str
            description: Annotated[str, ScrapeWins] = ""

            def on_update(self, old_db, new_db):
                if (
                    old_db is not None
                    and new_db is not None
                    and old_db.description != new_db.description
                ):
                    return [
                        FollowUp(
                            name="party-description-changed",
                            fn=lambda: None,
                        )
                    ]
                return None

        class _PartyTypeFull(InternalNode):
            natural_key = (parent.docket, "party", "role")
            party: _NoisyPartyRef
            role: str

        from cl.scrapers.mergers.tests.testmodels.models import TPartyType

        # Re-bind the InternalNode to the real model.
        _PartyTypeFull.__pydantic_generic_metadata__["args"] = (TPartyType,)

        class _DocketSchema(Aggregate[TDocket]):
            natural_key = ("court", "docket_number_core")
            court: PreResolvedRef[TCourt]
            docket_number_core: str
            party_types: list[_PartyTypeFull] = []

        scrape = _DocketSchema(
            court=self.court,
            docket_number_core="22-100",
            party_types=[
                _PartyTypeFull(
                    party=_NoisyPartyRef(
                        name="Existing", description="fresh"
                    ),
                    role="Witness",
                )
            ],
        )
        outcome = apply(reconcile(build_paired_tree(scrape)))

        names = [getattr(fu, "name", "") for fu in outcome.follow_ups]
        self.assertIn("party-description-changed", names)


# ---------------------------------------------------------------------------
# apply.py: NoopIfMissing absence policy
# ---------------------------------------------------------------------------


class NoopIfMissingTest(SimpleTestCase):
    """``NoopIfMissing`` ExternalNodeRef policy: when the lookup misses,
    the helper returns ``None`` rather than raising or creating.

    Tested by invoking ``_materialize_one_lookup_ref`` directly —
    integrating end-to-end through ``apply`` would require a test
    model with a nullable FK column to the ExternalNodeRef's target, which
    none of the testmodels provide.
    """

    def test_noop_if_missing_returns_none(self) -> None:
        class _OptionalPartyRef(
            ExternalNodeRef[TParty], absence_policy=NoopIfMissing
        ):
            natural_key = ("name",)
            name: str

        from cl.scrapers.mergers.apply import _materialize_one_lookup_ref
        from cl.scrapers.mergers.diff import CreateOp, DiffedNode

        scrape_ref = _OptionalPartyRef(name="Phantom")
        # Unresolved → db is None; framework would have produced a
        # CreateOp in reconcile but NoopIfMissing skips it.
        diffed = DiffedNode(
            scrape=scrape_ref,
            db=None,
            change=CreateOp(values={"name": "Phantom"}),
        )
        creates: dict = {}
        updates: dict = {}
        follow_ups: list = []
        cache: dict = {}
        result = _materialize_one_lookup_ref(
            diffed, creates, updates, follow_ups, cache
        )
        self.assertIsNone(result)
        # No DB write was attempted (creates dict stays empty).
        self.assertEqual(creates, {})
        # Cached as None so repeat resolutions short-circuit.
        self.assertIn(id(scrape_ref), cache)
        self.assertIsNone(cache[id(scrape_ref)])
