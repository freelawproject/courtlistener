"""Tests for :mod:`cl.scrapers.mergers.dedup`.

Each scalar / collection strategy maps to a specific fold semantic.
We exercise them in isolation here (calling
:func:`collapse_duplicate_scrape_nks` directly) and the integration
test at
:mod:`cl.scrapers.mergers.tests.test_duplicate_scrape_nk` covers the
end-to-end ``merge_one`` path.

Why a direct unit test in addition to the integration test: the fold
logic recurses through field descriptors and per-strategy branches
that are hard to fully exercise via real Django models. These tests
construct minimal Pydantic-only schemas (no Django) so each branch is
hit deterministically.
"""

from typing import Annotated, Any

from cl.scrapers.mergers.dedup import collapse_duplicate_scrape_nks
from cl.scrapers.mergers.nodes import InternalNode
from cl.scrapers.mergers.strategies import (
    Custom,
    CustomCollection,
    DBClobbers,
    DBWins,
    ScrapeClobbers,
    ScrapeWins,
    ScrapeWinsIfPresent,
    Union,
)
from cl.tests.cases import SimpleTestCase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _StubNode:
    """Stand-in for a parent / Django model in the NK key tuple. We
    never let the key function touch Django, so any sentinel works.
    """


# Note: we don't bind the InternalNode to a Django model — the fold
# logic doesn't introspect ``__django_model__`` and the test schemas
# don't get merged, only folded.


# ---------------------------------------------------------------------------
# Scalar strategies
# ---------------------------------------------------------------------------


class ScalarFoldTest(SimpleTestCase):
    """One test per scalar strategy variant."""

    def test_scrape_wins_uses_later_value(self) -> None:
        class _N(InternalNode, default_field=ScrapeWins):
            natural_key = ("k",)
            k: str
            v: str = ""

        out = collapse_duplicate_scrape_nks(
            [_N(k="A", v="first"), _N(k="A", v="second")],
            _N,
            key_fn=lambda x: (x.k,),
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].v, "second")

    def test_scrape_wins_if_present_keeps_first_when_later_is_none(
        self,
    ) -> None:
        class _N(InternalNode, default_field=ScrapeWinsIfPresent):
            natural_key = ("k",)
            k: str
            v: str | None = None

        out = collapse_duplicate_scrape_nks(
            [_N(k="A", v="kept"), _N(k="A", v=None)],
            _N,
            key_fn=lambda x: (x.k,),
        )
        self.assertEqual(out[0].v, "kept")

    def test_scrape_wins_if_present_uses_later_when_non_none(self) -> None:
        class _N(InternalNode, default_field=ScrapeWinsIfPresent):
            natural_key = ("k",)
            k: str
            v: str | None = None

        out = collapse_duplicate_scrape_nks(
            [_N(k="A", v=None), _N(k="A", v="later")],
            _N,
            key_fn=lambda x: (x.k,),
        )
        self.assertEqual(out[0].v, "later")

    def test_db_wins_keeps_first(self) -> None:
        class _N(InternalNode, default_field=DBWins):
            natural_key = ("k",)
            k: str
            v: str = ""

        out = collapse_duplicate_scrape_nks(
            [_N(k="A", v="first"), _N(k="A", v="ignored")],
            _N,
            key_fn=lambda x: (x.k,),
        )
        self.assertEqual(out[0].v, "first")

    def test_custom_scalar_strategy_is_called_with_scrape_and_db(
        self,
    ) -> None:
        """Custom(fn) gets fn(scrape=row_i+1, db=accumulator)."""
        calls: list[tuple[Any, Any]] = []

        def _fold(scrape: Any, db: Any) -> Any:
            calls.append((scrape, db))
            # Return a deterministic concat so we can assert the result.
            return f"{db}|{scrape}"

        class _N(InternalNode):
            natural_key = ("k",)
            k: str
            v: Annotated[str, Custom(_fold)] = ""

        out = collapse_duplicate_scrape_nks(
            [_N(k="A", v="first"), _N(k="A", v="second"), _N(k="A", v="third")],
            _N,
            key_fn=lambda x: (x.k,),
        )
        # Reduced left-to-right: first stays as acc, then fold(second, first),
        # then fold(third, prev).
        self.assertEqual(out[0].v, "first|second|third")
        self.assertEqual(calls, [("second", "first"), ("third", "first|second")])

    def test_no_collisions_returns_input_list_unchanged(self) -> None:
        """Fast-path: when there's no NK collision, the input is
        returned untouched (same identity)."""

        class _N(InternalNode):
            natural_key = ("k",)
            k: str

        items = [_N(k="A"), _N(k="B")]
        out = collapse_duplicate_scrape_nks(
            items, _N, key_fn=lambda x: (x.k,)
        )
        self.assertIs(out, items)


# ---------------------------------------------------------------------------
# Collection strategies (single-child)
# ---------------------------------------------------------------------------


class OptionalChildFoldTest(SimpleTestCase):
    """0-or-1 child slots fold per collection strategy."""

    def test_scrape_clobbers_optional_child_takes_later(self) -> None:
        class _Child(InternalNode):
            natural_key = ("k",)
            k: str
            v: str = ""

        class _Parent(InternalNode, default_collection=ScrapeClobbers):
            natural_key = ("k",)
            k: str
            child: _Child | None = None

        out = collapse_duplicate_scrape_nks(
            [
                _Parent(k="A", child=_Child(k="C1", v="first")),
                _Parent(k="A", child=_Child(k="C1", v="second")),
            ],
            _Parent,
            key_fn=lambda x: (x.k,),
        )
        self.assertEqual(out[0].child.v, "second")

    def test_union_optional_child_recurses_when_both_present(
        self,
    ) -> None:
        """With ``Union`` on the optional child slot AND both folded
        rows carrying a child, the children themselves get folded
        recursively per their own field strategies."""

        class _Child(InternalNode, default_field=ScrapeWins):
            natural_key = ("k",)
            k: str
            v: str = ""

        class _Parent(InternalNode, default_collection=Union):
            natural_key = ("k",)
            k: str
            child: _Child | None = None

        out = collapse_duplicate_scrape_nks(
            [
                _Parent(k="A", child=_Child(k="C1", v="first")),
                _Parent(k="A", child=_Child(k="C1", v="second")),
            ],
            _Parent,
            key_fn=lambda x: (x.k,),
        )
        # Inner scalar fold under ScrapeWins → later wins.
        self.assertEqual(out[0].child.v, "second")

    def test_union_optional_child_keeps_only_present_side(self) -> None:
        """One row has the child, the other doesn't — Union keeps it."""

        class _Child(InternalNode):
            natural_key = ("k",)
            k: str

        class _Parent(InternalNode, default_collection=Union):
            natural_key = ("k",)
            k: str
            child: _Child | None = None

        out = collapse_duplicate_scrape_nks(
            [
                _Parent(k="A", child=None),
                _Parent(k="A", child=_Child(k="X")),
            ],
            _Parent,
            key_fn=lambda x: (x.k,),
        )
        self.assertIsNotNone(out[0].child)
        self.assertEqual(out[0].child.k, "X")

    def test_db_clobbers_optional_child_keeps_first(self) -> None:
        class _Child(InternalNode):
            natural_key = ("k",)
            k: str

        class _Parent(InternalNode, default_collection=DBClobbers):
            natural_key = ("k",)
            k: str
            child: _Child | None = None

        out = collapse_duplicate_scrape_nks(
            [
                _Parent(k="A", child=_Child(k="first")),
                _Parent(k="A", child=_Child(k="ignored")),
            ],
            _Parent,
            key_fn=lambda x: (x.k,),
        )
        self.assertEqual(out[0].child.k, "first")


# ---------------------------------------------------------------------------
# Collection strategies (list-of-children)
# ---------------------------------------------------------------------------


class ChildListFoldTest(SimpleTestCase):
    """list[ChildNode] fields fold per collection strategy."""

    def test_scrape_clobbers_replaces_list(self) -> None:
        class _Item(InternalNode):
            natural_key = ("k",)
            k: str

        class _Parent(InternalNode, default_collection=ScrapeClobbers):
            natural_key = ("k",)
            k: str
            items: list[_Item] = []

        out = collapse_duplicate_scrape_nks(
            [
                _Parent(k="A", items=[_Item(k="x"), _Item(k="y")]),
                _Parent(k="A", items=[_Item(k="z")]),
            ],
            _Parent,
            key_fn=lambda x: (x.k,),
        )
        # Later wins entirely.
        self.assertEqual([c.k for c in out[0].items], ["z"])

    def test_db_clobbers_keeps_first_list(self) -> None:
        class _Item(InternalNode):
            natural_key = ("k",)
            k: str

        class _Parent(InternalNode, default_collection=DBClobbers):
            natural_key = ("k",)
            k: str
            items: list[_Item] = []

        out = collapse_duplicate_scrape_nks(
            [
                _Parent(k="A", items=[_Item(k="x")]),
                _Parent(k="A", items=[_Item(k="y"), _Item(k="z")]),
            ],
            _Parent,
            key_fn=lambda x: (x.k,),
        )
        self.assertEqual([c.k for c in out[0].items], ["x"])

    def test_union_list_combines_and_dedupes_by_nk(self) -> None:
        """``Union`` concatenates, then recursively dedupes by NK in
        the merged set. Duplicate items inside the union fold via the
        same per-field rules."""

        class _Item(InternalNode, default_field=ScrapeWins):
            natural_key = ("k",)
            k: str
            v: str = ""

        class _Parent(InternalNode, default_collection=Union):
            natural_key = ("k",)
            k: str
            items: list[_Item] = []

        out = collapse_duplicate_scrape_nks(
            [
                _Parent(
                    k="A",
                    items=[_Item(k="x", v="x-from-first"), _Item(k="y", v="y-from-first")],
                ),
                _Parent(
                    k="A",
                    items=[_Item(k="y", v="y-from-second"), _Item(k="z", v="z-only")],
                ),
            ],
            _Parent,
            key_fn=lambda x: (x.k,),
        )
        merged = {c.k: c.v for c in out[0].items}
        # x present from first, z from second, y folded under ScrapeWins
        # (later wins).
        self.assertEqual(
            merged,
            {"x": "x-from-first", "y": "y-from-second", "z": "z-only"},
        )

    def test_custom_collection_falls_back_to_scrape_clobbers(self) -> None:
        """``CustomCollection`` doesn't fit the scrape-vs-scrape fold
        cleanly; documented fallback is ScrapeClobbers semantics."""

        def _unused(pairs, scrape_only, db_only):  # pragma: no cover
            raise AssertionError("fn must not be called during fold")

        class _Item(InternalNode):
            natural_key = ("k",)
            k: str

        class _Parent(
            InternalNode, default_collection=CustomCollection(_unused)
        ):
            natural_key = ("k",)
            k: str
            items: list[_Item] = []

        out = collapse_duplicate_scrape_nks(
            [
                _Parent(k="A", items=[_Item(k="x")]),
                _Parent(k="A", items=[_Item(k="y")]),
            ],
            _Parent,
            key_fn=lambda x: (x.k,),
        )
        # ScrapeClobbers fallback: later list wins.
        self.assertEqual([c.k for c in out[0].items], ["y"])


# ---------------------------------------------------------------------------
# Multi-row fold (more than two duplicates)
# ---------------------------------------------------------------------------


class MultiRowFoldTest(SimpleTestCase):
    """Folds reduce left-to-right across N rows, not just 2."""

    def test_three_duplicate_rows_under_scrape_wins(self) -> None:
        class _N(InternalNode, default_field=ScrapeWins):
            natural_key = ("k",)
            k: str
            v: str = ""

        out = collapse_duplicate_scrape_nks(
            [
                _N(k="A", v="1"),
                _N(k="A", v="2"),
                _N(k="A", v="3"),
            ],
            _N,
            key_fn=lambda x: (x.k,),
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].v, "3")

    def test_mixed_nks_with_some_duplicates(self) -> None:
        """Rows with distinct NKs pass through; only same-NK rows fold."""

        class _N(InternalNode, default_field=ScrapeWins):
            natural_key = ("k",)
            k: str
            v: str = ""

        out = collapse_duplicate_scrape_nks(
            [
                _N(k="A", v="a1"),
                _N(k="B", v="b1"),
                _N(k="A", v="a2"),
                _N(k="C", v="c1"),
                _N(k="A", v="a3"),
            ],
            _N,
            key_fn=lambda x: (x.k,),
        )
        # Order-preserving: A first (folded), B second, C third.
        self.assertEqual([(r.k, r.v) for r in out], [("A", "a3"), ("B", "b1"), ("C", "c1")])
