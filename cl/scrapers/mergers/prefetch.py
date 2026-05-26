"""Phase 2 — Prefetch.

Resolves natural-key lookups against the database. ``prefetch_root`` is
the simplest case (no parent context, single query); child prefetch
will build on it in L4b with per-model batching.

See cl/scrapers/MERGERS_IN_THEORY.md (4-phase model section).
"""

from typing import Any

from cl.scrapers.mergers.nk import (
    OwnScalar,
    ParentPath,
    SiblingRef,
    classify_nk,
)
from cl.scrapers.mergers.nodes import Aggregate, bound_django_model


def prefetch_root[ModelT](
    scrape_root: Aggregate[ModelT],
    *,
    prefetch_paths: list[str] | None = None,
) -> ModelT | None:
    """Query the Aggregate's bound Django model for the row matching
    ``scrape_root``'s natural key.

    Returns the matched DB instance, or ``None`` if no row matches.

    If the Aggregate declares ``lock_for_update=True``, the query uses
    ``select_for_update()`` (caller must be in an atomic block).

    If ``prefetch_paths`` is given, the queryset is augmented with
    ``prefetch_related(*paths)`` so downstream tree-walking can read
    related rows without further DB hits.

    :raises ValueError: if the schema's NK references a parent path
        (Aggregates have no parent) or if no Django model is bound.
    """
    cls = type(scrape_root)
    model = bound_django_model(cls)
    if model is None:
        raise ValueError(
            f"{cls.__name__} has no bound Django model — can't prefetch."
        )

    filter_kwargs = _build_root_filter(scrape_root)

    queryset = model._default_manager.filter(**filter_kwargs)
    if cls._mergers_lock_for_update:
        queryset = queryset.select_for_update()
    if prefetch_paths:
        queryset = queryset.prefetch_related(*prefetch_paths)
    return queryset.first()


def _build_root_filter(scrape_root: Aggregate[Any]) -> dict[str, Any]:
    """Build the ``.filter(**kwargs)`` dict for a root NK lookup.

    Each NK element contributes one kwarg:
    - ``OwnScalar``: ``field_name=scrape.field_name``
    - ``SiblingRef``: ``field_name=scrape.field_name`` (ORM accepts the
      resolved Django instance directly; Django extracts the PK).

    ``ParentPath`` is rejected — Aggregates have no parent.
    """
    cls = type(scrape_root)
    kwargs: dict[str, Any] = {}
    for element in classify_nk(cls):
        if isinstance(element, ParentPath):
            raise ValueError(
                f"{cls.__name__}.natural_key references a parent path "
                f"({element.path!r}), but Aggregates have no parent."
            )
        if isinstance(element, OwnScalar):
            kwargs[element.field_name] = getattr(
                scrape_root, element.field_name
            )
        elif isinstance(element, SiblingRef):
            kwargs[element.field_name] = getattr(
                scrape_root, element.field_name
            )
    return kwargs
