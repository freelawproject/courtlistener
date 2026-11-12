from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Model


@dataclass
class RelatedParams[ParamType]:
    """Wrapper for passing parameters to a related object.

    Attributes:
        params: The parameters passed by the user to the merger
        parent: The object the related object hangs off of
        parent_name: The name of the child's field pointing back at
            `parent`, set for the reverse side of a one-to-one relation. The child
            merger fills that field in from `parent` itself, so a child merger
            must not declare it.
    """

    params: ParamType
    parent: Model | None = field(kw_only=True)
    parent_name: str | None = field(kw_only=True, default=None)


@dataclass
class ThroughParameters[ParamType](RelatedParams[ParamType]):
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
    params: ParamType
