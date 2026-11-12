from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Model
from typing_extensions import Sentinel


@dataclass
class RelatedParams[Params]:
    """Wrapper for passing parameters to a related object.

    Attributes:
        params: The parameters passed by the user to the merger
        parent: The object the related object hangs off of
        parent_name: The name of the child's field pointing back at
            `parent`, set for the reverse side of a one-to-one relation. The child
            merger fills that field in from `parent` itself, so a child merger
            must not declare it.
    """

    params: Params
    parent: Model | None = field(kw_only=True)
    parent_name: str | None = field(kw_only=True, default=None)


@dataclass
class ThroughParameters[Params](RelatedParams[Params]):
    """Wrapper for passing parameters to a `through` model.

    Attributes:
        source: The source object of the relationship
        target: The target object of the relationship
        params: The parameters passed by the user to the merger
    """

    source: Model = field(kw_only=True)
    source_name: str = field(kw_only=True)
    target: Model = field(kw_only=True)
    target_name: str = field(kw_only=True)
    params: Params


Lookup = Sentinel("Lookup")
"""Find the object to merge into in the DB, creating it if there is none."""
Create = Sentinel("Create")
"""Skip the lookup and create a new object."""


@dataclass(slots=True)
class Update[M: Model]:
    """Skip the lookup and merge into a known object.

    :ivar instance: The object to merge into."""

    instance: M


type Existing[M: Model] = Lookup | Create | Update[M]
