"""Pure reconciliation functions.

Phase 3 (and supporting primitives): apply a scalar strategy to a single
field, apply a collection strategy to a Pairing.

These functions are pure: no DB access, no side effects.

See cl/scrapers/MERGERS_IN_THEORY.md (Strategies section).
"""

from collections import defaultdict
from collections.abc import Callable, Iterable
from itertools import combinations, permutations
from typing import Any

from cl.scrapers.mergers.ops import (
    Create,
    Delete,
    NoChange,
    Op,
    Pairing,
    ScalarDecision,
    Update,
    Write,
)
from cl.scrapers.mergers.strategies import (
    CollectionStrategy,
    Custom,
    CustomCollection,
    ScalarStrategy,
    _DBClobbers,
    _DBWins,
    _ScrapeClobbers,
    _ScrapeWins,
    _ScrapeWinsIfPresent,
    _Union,
)


def apply_scalar_strategy(
    strategy: ScalarStrategy, scrape_val: Any, db_val: Any
) -> ScalarDecision[Any]:
    """Apply a scalar field strategy.

    Returns ``Write(value)`` if the DB should be updated, else
    ``NoChange``.

    The equality check is strict ``==``. Normalization is the scraper's
    responsibility (see the Equality section of MERGERS_IN_THEORY.md).

    :raises TypeError: if ``strategy`` is not a ``ScalarStrategy``.
    """
    if isinstance(strategy, _ScrapeWins):
        return Write(scrape_val) if scrape_val != db_val else NoChange

    if isinstance(strategy, _ScrapeWinsIfPresent):
        if scrape_val is None:
            return NoChange
        return Write(scrape_val) if scrape_val != db_val else NoChange

    if isinstance(strategy, _DBWins):
        return NoChange

    if isinstance(strategy, Custom):
        new_val = strategy.fn(scrape_val, db_val)
        return Write(new_val) if new_val != db_val else NoChange

    raise TypeError(f"Not a scalar strategy: {strategy!r}")


def pair_by_nk[ScrapeT, DBT, K](
    scrape_items: Iterable[ScrapeT],
    db_items: Iterable[DBT],
    key_fn: Callable[[Any], K],
) -> Pairing[ScrapeT, DBT]:
    """Hash-join ``scrape_items`` against ``db_items`` on natural key.

    O(n + m) where n = ``len(scrape_items)``, m = ``len(db_items)``.

    The key returned by ``key_fn`` must be hashable. Both sides must
    have distinct NKs — duplicates raise ``ValueError`` (handle the
    duplicate case via ``allow_duplicates=True`` at the node level).

    Order preservation:
    - ``pairs`` follows scrape iteration order.
    - ``scrape_only`` follows scrape iteration order.
    - ``db_only`` follows DB iteration order.
    """
    scrape_list = list(scrape_items)
    db_list = list(db_items)

    # Build hash index of DB by NK, detecting duplicates.
    db_by_key: dict[K, DBT] = {}
    for d in db_list:
        k = key_fn(d)
        if k in db_by_key:
            raise ValueError(f"duplicate DB natural key: {k!r}")
        db_by_key[k] = d

    pairs: list[tuple[ScrapeT, DBT]] = []
    scrape_only: list[ScrapeT] = []
    seen_scrape_keys: set[K] = set()
    matched_db_keys: set[K] = set()

    for s in scrape_list:
        k = key_fn(s)
        if k in seen_scrape_keys:
            raise ValueError(f"duplicate scrape natural key: {k!r}")
        seen_scrape_keys.add(k)
        d = db_by_key.get(k)
        if d is not None or k in db_by_key:
            # Use `k in db_by_key` to handle the case where d is None
            # (the DB item itself is None, unlikely but possible).
            pairs.append((s, db_by_key[k]))
            matched_db_keys.add(k)
        else:
            scrape_only.append(s)

    db_only = [d for d in db_list if key_fn(d) not in matched_db_keys]

    return Pairing(pairs=pairs, scrape_only=scrape_only, db_only=db_only)


def apply_collection_strategy[ScrapeT, DBT](
    strategy: CollectionStrategy, pairing: Pairing[ScrapeT, DBT]
) -> list[Op[ScrapeT, DBT]]:
    """Convert a Pairing into a list of ops per the collection strategy.

    For every named strategy, pairs always produce ``Update`` (per-field
    scalar strategies during the reconcile walk decide what actually
    writes). The strategies only differ in how unmatched buckets are
    handled.

    :raises TypeError: if ``strategy`` is not a ``CollectionStrategy``.
    """
    if isinstance(strategy, _ScrapeClobbers):
        return [
            *(Update(s, d) for s, d in pairing.pairs),
            *(Create(s) for s in pairing.scrape_only),
            *(Delete(d) for d in pairing.db_only),
        ]
    if isinstance(strategy, _DBClobbers):
        return [Update(s, d) for s, d in pairing.pairs]
    if isinstance(strategy, _Union):
        return [
            *(Update(s, d) for s, d in pairing.pairs),
            *(Create(s) for s in pairing.scrape_only),
        ]
    if isinstance(strategy, CustomCollection):
        return strategy.fn(
            pairing.pairs, pairing.scrape_only, pairing.db_only
        )
    raise TypeError(f"Not a collection strategy: {strategy!r}")


def pair_by_nk_allowing_duplicates[ScrapeT, DBT, K](
    scrape_items: Iterable[ScrapeT],
    db_items: Iterable[DBT],
    key_fn: Callable[[Any], K],
    edit_cost_fn: Callable[[ScrapeT, DBT], int],
) -> Pairing[ScrapeT, DBT]:
    """Pair scrape items to DB items by NK, allowing duplicates per NK.

    Within each NK bucket, the matching is chosen to minimize total
    ``edit_cost_fn`` across paired items. When buckets are uneven, the
    extra items go to ``scrape_only`` / ``db_only``.

    Items with NKs that exist on only one side go entirely to that
    side's bucket.

    Complexity: O(b * k!) brute-force per bucket, where k = min bucket
    size. Suitable for typical CL data (small buckets); swap in a
    polynomial-time assignment algorithm if larger buckets show up.

    :param edit_cost_fn: ``(scrape_item, db_item) -> non-negative int``.
        Lower means better match. The function is only called for
        same-NK pairs.
    """
    scrape_buckets: dict[K, list[ScrapeT]] = defaultdict(list)
    for s in scrape_items:
        scrape_buckets[key_fn(s)].append(s)
    db_buckets: dict[K, list[DBT]] = defaultdict(list)
    for d in db_items:
        db_buckets[key_fn(d)].append(d)

    pairs: list[tuple[ScrapeT, DBT]] = []
    scrape_only: list[ScrapeT] = []
    db_only: list[DBT] = []

    for k in scrape_buckets.keys() | db_buckets.keys():
        s_bucket = scrape_buckets.get(k, [])
        d_bucket = db_buckets.get(k, [])
        if not d_bucket:
            scrape_only.extend(s_bucket)
            continue
        if not s_bucket:
            db_only.extend(d_bucket)
            continue
        b_pairs, b_scrape_only, b_db_only = _min_cost_assignment(
            s_bucket, d_bucket, edit_cost_fn
        )
        pairs.extend(b_pairs)
        scrape_only.extend(b_scrape_only)
        db_only.extend(b_db_only)

    return Pairing(pairs=pairs, scrape_only=scrape_only, db_only=db_only)


def _min_cost_assignment[ScrapeT, DBT](
    scrape: list[ScrapeT],
    db: list[DBT],
    cost_fn: Callable[[ScrapeT, DBT], int],
) -> tuple[list[tuple[ScrapeT, DBT]], list[ScrapeT], list[DBT]]:
    """Brute-force minimum-cost bipartite assignment.

    Returns ``(pairs, unpaired_scrape, unpaired_db)``.
    """
    n, m = len(scrape), len(db)
    k = min(n, m)
    if k == 0:
        return [], list(scrape), list(db)

    best_cost: int | None = None
    best_assignment: tuple[tuple[int, ...], tuple[int, ...]] | None = None
    for s_idx in combinations(range(n), k):
        for d_perm in permutations(range(m), k):
            c = sum(
                cost_fn(scrape[s_idx[i]], db[d_perm[i]])
                for i in range(k)
            )
            if best_cost is None or c < best_cost:
                best_cost = c
                best_assignment = (s_idx, d_perm)

    assert best_assignment is not None  # k > 0 ensures we ran the loop
    s_idx, d_perm = best_assignment
    pairs = [(scrape[s_idx[i]], db[d_perm[i]]) for i in range(k)]
    paired_s = set(s_idx)
    paired_d = set(d_perm)
    return (
        pairs,
        [scrape[i] for i in range(n) if i not in paired_s],
        [db[i] for i in range(m) if i not in paired_d],
    )
