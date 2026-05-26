"""Schema validation.

``validate_schema(cls)`` runs schema-level checks on a Node subclass
and raises ``SchemaError`` if anything is wrong. The framework invokes
it explicitly before using a schema (e.g., at the entrance of phase 2).

Validation is *not* automatic at class-definition time: tests and other
non-merge consumers may define partial classes that don't satisfy all
checks, and running validation lazily lets those use cases work without
forcing every fixture to declare a full NK. The orchestrator (L7) calls
``validate_schema(root_class)`` once per merge to catch errors at the
moment of use.

Checks:
- ``natural_key`` is declared and valid (delegated to ``classify_nk``).
- A non-Optional single ``ChildField`` referencing a ``ExternalNodeRef`` with
  ``absence_policy=NoopIfMissing`` is forbidden — the parent FK would
  be required but the policy says leave it null.

See cl/scrapers/MERGERS_IN_THEORY.md.
"""

from cl.scrapers.mergers.fields import ChildField, extract_fields
from cl.scrapers.mergers.nk import classify_nk
from cl.scrapers.mergers.nodes import ExternalNodeRef, Node, NoopIfMissing


class SchemaError(Exception):
    """Raised when a Node subclass declaration is invalid."""


def validate_schema(cls: type[Node]) -> None:
    """Run all schema-level checks on ``cls``.

    :raises SchemaError: on any violation.
    """
    try:
        classify_nk(cls)
    except ValueError as e:
        raise SchemaError(str(e)) from e

    for f in extract_fields(cls):
        if isinstance(f, ChildField):
            child = f.child_class
            if (
                issubclass(child, ExternalNodeRef)
                and child._mergers_absence_policy is NoopIfMissing
                and not f.is_optional
            ):
                raise SchemaError(
                    f"{cls.__name__}.{f.name} is a non-Optional ExternalNodeRef "
                    f"to {child.__name__}, but {child.__name__} declares "
                    f"absence_policy=NoopIfMissing. The parent FK would "
                    f"have to be NULL but the field requires a value. "
                    f"Either make the field Optional or change the "
                    f"absence_policy."
                )
