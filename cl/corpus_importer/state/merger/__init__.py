"""Declarative mergers that reconcile scraped state court data with the database."""

from . import state as MergerState
from .base import (
    Merger,
    MergerConfig,
    auto_now_fields,
)
from .match import (
    Fail,
    First,
    Key,
    Match,
    Narrow,
    Next,
)
from .parameters import (
    Create,
    Lookup,
    RelatedParams,
    ThroughParameters,
    Update,
)
from .pool import (
    Global,
    Pool,
    Relatives,
    Siblings,
)
from .specifications import (
    Ancestor,
    Annotation,
    Coalesce,
    Constant,
    Database,
    Fn,
    ManyStrategy,
    ManyToManyRelation,
    OneToManyRelation,
    OneToOneRelation,
    Params,
    Scrape,
)

__all__ = [
    "Ancestor",
    "Annotation",
    "Coalesce",
    "Constant",
    "Create",
    "Database",
    "Fail",
    "First",
    "Fn",
    "Global",
    "Key",
    "Lookup",
    "ManyStrategy",
    "ManyToManyRelation",
    "Match",
    "Merger",
    "MergerConfig",
    "MergerState",
    "Narrow",
    "Next",
    "OneToManyRelation",
    "OneToOneRelation",
    "Params",
    "Pool",
    "RelatedParams",
    "Relatives",
    "Scrape",
    "Siblings",
    "ThroughParameters",
    "Update",
    "auto_now_fields",
]
