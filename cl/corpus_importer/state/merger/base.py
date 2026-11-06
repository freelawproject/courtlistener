from __future__ import annotations

import json
import logging
from collections.abc import (
    Iterable,
    MutableMapping,
    Sequence,
)
from functools import cache, reduce
from typing import (
    Any,
    ClassVar,
    Self,
    cast,
)

from django.db import transaction
from django.db.models import (
    Model,
    QuerySet,
)
from django.db.models.manager import Manager

from cl.corpus_importer.state.utils import MergeResult

from .parameters import (
    RelatedParams,
    ThroughParameters,
)
from .specifications import (
    AttributeMerger,
    MergerSpecification,
    OneToOneMerger,
    RelatedMerger,
)

logger = logging.getLogger(__name__)


@cache
def auto_now_fields(model: type[Model]) -> tuple[str, ...]:
    """Collect the names of a model's `auto_now` fields (e.g. `date_modified`).

    Args:
        model: The model to inspect.

    Returns:
        The names of every concrete `auto_now` field on the model.
    """
    return tuple(
        f.name
        for f in model._meta.concrete_fields
        if getattr(f, "auto_now", False)
    )


class MergerSpecRegistry[ScrapeType, ParamType]:
    def __init__(
        self,
        *,
        related: dict[
            str, RelatedMerger[ScrapeType, ParamType, Any, Any, Model]
        ]
        | None = None,
        attr: dict[str, AttributeMerger[ScrapeType, ParamType, Any]]
        | None = None,
        one_to_one: dict[
            str, OneToOneMerger[ScrapeType, ParamType, Any, Model]
        ]
        | None = None,
    ):
        self.related: dict[
            str, RelatedMerger[ScrapeType, ParamType, Any, Any, Model]
        ] = related or {}
        self.attr: dict[str, AttributeMerger[ScrapeType, ParamType, Any]] = (
            attr or {}
        )
        self.one_to_one: dict[
            str, OneToOneMerger[ScrapeType, ParamType, Any, Model]
        ] = one_to_one or {}

    def __copy__(self) -> Self:
        return self.__class__(
            related=self.related, attr=self.attr, one_to_one=self.one_to_one
        )

    def __or__(self, other: Self) -> Self:
        return self.__class__(
            related=self.related | other.related,
            attr=self.attr | other.attr,
            one_to_one=self.one_to_one | other.one_to_one,
        )

    def validate(
        self, merger: type[Merger[ScrapeType, ParamType, Any]]
    ) -> list[Exception]:
        """Run validation for every attached spec against the given merger.

        Used to defer running validation on base classes which may not have
        required properties defined yet.

        Validation is also the first point at which a one-to-one spec knows
        which side of the relation it is on, so reverse specs are moved into
        `related` here: they can only be merged once their parent exists, which
        is when the `related` specs run.
        """
        errors = []

        for related_spec in self.related.values():
            errors += related_spec.run_validation(merger)

        for attr_spec in self.attr.values():
            errors += attr_spec.run_validation(merger)

        for name, one_to_one_spec in list(self.one_to_one.items()):
            errors += one_to_one_spec.run_validation(merger)
            if not one_to_one_spec.forward:
                del self.one_to_one[name]
                self.related[name] = one_to_one_spec

        return errors

    def update(self, other: Self):
        self.related.update(other.related)
        self.attr.update(other.attr)
        self.one_to_one.update(other.one_to_one)

    def register(self, spec: MergerSpecification[ScrapeType, ParamType, Any]):
        match spec:
            case AttributeMerger():
                self.attr[spec.name] = spec
            case OneToOneMerger():
                self.one_to_one[spec.name] = spec
            case RelatedMerger():
                self.related[spec.name] = spec
            case _:
                logger.error(f"Unknown merger spec type: {spec}")


class MergerMeta(type):
    @classmethod
    def __prepare__(
        cls,
        name: str,
        bases: tuple[type, ...],
        /,
        abstract: bool = False,
        **kwargs,
    ) -> MutableMapping[str, object]:
        # We need this so that merger subclassing works like you'd expect.
        # Because we're efficient and don't check for specifications on every merge, we need to keep a cache. A
        # dictionary would be a great cache! Unfortunately, when you subclass, that dictionary is not reinitialized
        # so you need to copy it to avoid polluting your base class with your subclass' specs. We can't do this copy in
        # Merger.__init_subclass__ since that runs after all MergerSpecification.__set_name__ calls, so we have to do it
        # here.
        # "Why not just register merger specs in __init_subclass__ then?" I hear you ask. I tried this, but it required
        # filtering class attributes before registration, which felt messy, and it just made the __init_subclass__ body
        # too big and confusing.
        registry: MergerSpecRegistry[Any, Any] = MergerSpecRegistry()
        for base in bases:
            if hasattr(base, "__registry__") and isinstance(
                base.__registry__, MergerSpecRegistry
            ):
                registry |= base.__registry__
        return {
            **type.__prepare__(name, bases, **kwargs),
            "__registry__": registry,
            "errors": [],
        }


class Merger[ScrapeType, ParamType, M: Model](metaclass=MergerMeta):
    """Base class for a merger which takes in `D` and merges it into `model`.

    Subclasses should generally not be instantiated; methods and attributes
    should be accessed directly from the class.

    Attributes:
        model: The model this merger applies to.
        atomic: Whether to wrap the entire merge operation -- the object's own attributes *and* all related/child
            mergers -- in a single `transaction.atomic()` block, so the whole tree commits together or rolls back together
            if an exception is raised. Nested mergers that set their own `atomic` value simply create savepoints within
            this block.
        key: A natural key to use for looking up objects in the DB; used in the default `get_existing` implementation.
        errors: A list of errors encountered during validation of this merger. These will be surfaced after the merger
            is fully constructed and will prevent the `merge` method from being called.
        scrape: Data from scrape with no modifications
        params: Parameters passed to the merger
        transformed: Data from scrape after being run through all the transforms for attribute and related mergers
        existing: A matching object in the DB or `None` if not found. Initialized lazily
        result: Stores the result of the attempted merge operation. Initialized to `None` and updated when the
            merge attempt completes. If the input data is invalid, the result will instead be set to `MergeResult.failed`
        out: The object written to the DB or `None` if the merge failed. Initialized as `None` and updated after
            the merge attempt completes
    """

    model: ClassVar[type[Model]]
    atomic: ClassVar[bool] = False
    key: ClassVar[Iterable[str]] = []
    errors: ClassVar[list[Exception]]
    __registry__: ClassVar[MergerSpecRegistry[Any, Any]]

    def __init_subclass__(cls, abstract: bool = False) -> None:
        """Initialize a merger subclass.

        Args:
            abstract: Whether this merger is abstract and should not be instantiated/validated.
        """
        super().__init_subclass__()

        if abstract:
            logger.info(
                "Skipping validation of abstract merger: %s", cls.__name__
            )
            return

        cls.errors += cls.__registry__.validate(cls)

        model_fields = cls.model._meta.get_fields()
        fields = {field.name: field for field in model_fields}

        for name in cls.__registry__.related.keys():
            attname = getattr(fields[name], "attname", None)
            if attname is not None and attname in cls.__registry__.attr:
                cls.errors.append(
                    TypeError(
                        f"Cannot merge both {name} and {attname} on {cls.model.__name__}"
                    )
                )

        cls.guarantee_valid()

    @classmethod
    def guarantee_valid(cls):
        if cls.errors:
            raise TypeError(
                "Invalid merger configuration for {}:\n{}".format(
                    cls.model.__name__,
                    "\n".join(f"- {repr(e)}" for e in cls.errors),
                )
            )

    @classmethod
    def uses_natural_key(cls) -> bool:
        """Check if the implementor has overridden the query method.

        This is useful because natural keys allow us to use some nice
        optimizations when merging N-to-many relations.
        """
        return (
            cls.query == Merger.query
            and cls.resolve_query == Merger.resolve_query
        )

    @classmethod
    def init_many(
        cls,
        scrapes: Sequence[ScrapeType],
        *,
        params: ParamType | Sequence[ParamType],
        manager: Manager[M] | None = None,
    ) -> tuple[MergeResult[Any], list[Self]]:
        result = MergeResult.unnecessary()
        if isinstance(params, Sequence):
            if len(params) != len(scrapes):
                logger.error(
                    "Different number of params and scrape entries for merger %s (%s != %s)",
                    cls.__name__,
                    len(params),
                    len(scrapes),
                )
            mergers = [
                cls(scrape, params=param, manager=manager, lookup=True)
                for scrape, param in zip(scrapes, params)
            ]
        else:
            mergers = [
                cls(scrape, params=params, manager=manager, lookup=True)
                for scrape in scrapes
            ]
        if not cls.uses_natural_key():
            return result, mergers

        merger_hashed: dict[int, Self] = {}
        for merger in mergers:
            merger.lookup = False
            if merger.result is not None:
                result |= merger.result
                continue
            k = merger._hash_natural_key_transform()
            if k in merger_hashed:
                logger.error(
                    "Multiple scraped instances with same natural key for model %s",
                    merger.model.__name__,
                )
                merger_hashed[k].result = MergeResult.failed(
                    merger_hashed[k].model.__name__
                )
                result |= MergeResult.failed(merger.model.__name__)
            merger_hashed[k] = merger

        if not merger_hashed:
            return result, mergers

        query = reduce(
            lambda q1, q2: q1 | q2,
            (
                merger.query().filter(**merger._relation_params)
                for merger in merger_hashed.values()
            ),
        )
        relation_names = next(iter(merger_hashed.values()))._relation_params
        for obj in query.iterator():
            k = cls._hash_natural_key_model(obj, relation_names)
            if k in merger_hashed:
                if merger_hashed[k].existing is not None:
                    logger.error(
                        "Found multiple matching objects for natural key of %s",
                        merger_hashed[k].model.__name__,
                    )
                    merger_hashed[k].result = MergeResult.failed(
                        merger_hashed[k].model.__name__
                    )
                    result |= MergeResult.failed(
                        merger_hashed[k].model.__name__
                    )
                    continue
                merger_hashed[k].existing = obj
        return result, mergers

    @staticmethod
    def validate(scrape: ScrapeType) -> bool:
        """Validate the input data before attempting a merge operation.

        Args:
            scrape: Input data to the merge

        Returns:
            True if the input is valid and the merge operation can proceed. False if the merge operation should be
            canceled.
        """
        return True

    def __init__(
        self,
        scrape: ScrapeType,
        *,
        params: ParamType,
        existing: M | None = None,
        manager: Manager[M] | None = None,
        lookup: bool = True,
    ):
        """Create an object to track the merge operation on the specified data.

        Args:
            scrape: The scraped data to transform. Parameter values are passed as kwargs.
            params: The parameters this merger was given by its parent.
            existing: Optional existing object to override the lookup in `get_existing`.
            manager: The manager to use for lookups and creation of objects. Defaults to the model's default manager.
            lookup: Whether the merger should attempt to lookup missing objects. Useful for optimizing queries in
                N-to-many relations.
        """
        self.guarantee_valid()
        result = None
        valid = self.validate(scrape)
        if not valid:
            logger.error(
                f"Merger {self.__class__.__name__} received invalid input."
            )
            result = MergeResult.failed(self.model.__name__)

        self.scrape: ScrapeType = scrape
        self.params: ParamType = params
        self.result: MergeResult[Any] | None = result
        self.out: M | None = None

        self.transformed: dict[str, Any] = (
            {
                name: spec.transform(scrape, params)
                for name, spec in self.__registry__.attr.items()
            }
            | {
                name: spec.transform(scrape, params)
                for name, spec in self.__registry__.related.items()
            }
            | {
                name: spec.transform(scrape, params)
                for name, spec in self.__registry__.one_to_one.items()
            }
            if valid
            else {}
        )

        # Relations the merger fills in itself rather than leaving to a spec: a
        # `through` model's two ends, or the foreign key a reverse one-to-one
        # child points back at its parent with. They are set on create, kept on
        # update, and narrow the lookup for an existing object.
        # It's hacky but it works.
        relation_params: dict[str, Model] = {}
        if isinstance(params, ThroughParameters):
            relation_params = {
                params.source_name: params.source,
                params.target_name: params.target,
            }
        elif (
            isinstance(params, RelatedParams)
            and params.parent_name is not None
            and params.parent is not None
        ):
            relation_params = {params.parent_name: params.parent}
        self._relation_params: dict[str, Model] = relation_params

        if manager is None:
            manager = cast(Manager[M], self.model._default_manager)
        self.manager: Manager[M] = manager

        self.existing: M | None = existing
        self.lookup: bool = lookup

    def _hash_natural_key_transform(self) -> int:
        return hash(
            json.dumps(
                {name: str(self.transformed[name]) for name in self.key}
                | {
                    name: str(obj.pk)
                    for name, obj in self._relation_params.items()
                },
                sort_keys=True,
            )
        )

    @classmethod
    def _hash_natural_key_model(
        cls, obj: M, relation_names: Iterable[str] = ()
    ) -> int:
        return hash(
            json.dumps(
                {name: str(getattr(obj, name)) for name in cls.key}
                | {
                    name: str(getattr(obj, f"{name}_id"))
                    for name in relation_names
                },
                sort_keys=True,
            )
        )

    def pre_update(self, updated_fields: list[str]) -> list[str]:
        """Called before an updated instance is saved. Useful for setting attributes that are dependent on the result of the merge operation.

        Args:
            updated_fields: The fields that were updated.

        Returns:
            A list of additional attribute names that should be updated.
        """
        return []

    def needs_update(self) -> bool:
        """Whether `self.existing` should take the update path even when no merged attribute changed. Useful for re-triggering downstream processing (e.g. a re-download) driven by the merge result's updates.

        Returns:
            True to force the update path.
        """
        return False

    def after(self) -> None:
        """Run extra processes after the merge operation completes or fails."""
        ...

    def query(self) -> QuerySet[M]:
        """Constructs a queryset to find an existing object in the DB, using the natural key defined by `cls.key`.

        The `merge` method will limit the queryset to returning at most two objects. If the queryset returns more than
        one object, the `resolve_query` method will be called to determine which object (if any) to merge into.

        Returns:
            The queryset to find the object.
        """
        return self.manager.filter(
            **{name: self.transformed[name] for name in self.key},
        )

    def resolve_query(self, qs: QuerySet[M]) -> tuple[bool, M | None]:
        """Called to resolve the output of `self.query()` into a single object to be merged. Returns a tuple where the first entry is a boolean indicating whether the merge can continue and the second is a DB object or `None`. If the query cannot continue, the `merge` method will return a failed result and cancel. If `None` is returned as the DB object, a new object will be created. This method should be deterministic and always return the same output for the same inputs to ensure merge operations are idempotent."""
        results = list(qs)
        if len(results) == 0:
            return True, None
        if len(results) == 1:
            return True, results[0]
        return False, None

    def merge(self) -> MergeResult[Any]:
        """Merge scraped data into the DB."""
        if self.result is not None:
            return self.result
        if self.existing is None and self.lookup:
            qs = self.query()
            # Filtering invalidates the cache even if the filter is empty. Try to avoid that.
            if self._relation_params:
                qs = qs.filter(**self._relation_params)
            if qs._result_cache is None:
                qs = qs[:2]
            valid, self.existing = self.resolve_query(qs)
            if not valid:
                logger.error(
                    "Merger %s found multiple objects; skipping merge.",
                    self.__class__.__name__,
                )
                self.result = MergeResult.failed(self.model.__name__)
                return self.result

        if self.atomic:
            with transaction.atomic():
                result, out_obj = self.merge_one()
        else:
            result, out_obj = self.merge_one()
        self.result = result
        self.out = out_obj
        self.after()
        return result

    def update_existing(self) -> MergeResult[Any]:
        """Merge attributes and 1-1 relations into `self.existing` in-place."""
        obj = cast(
            M,
            self.model(
                **(
                    {
                        name: self.transformed[name]
                        for name in self.__registry__.attr.keys()
                    }
                    | self._relation_params
                ),
            ),
        )

        if self.existing is None:
            raise ValueError("Cannot merge object into None")
        updated: list[str] = []
        for name, spec in self.__registry__.attr.items():
            obj_v = getattr(obj, name)
            db_v = getattr(self.existing, name)
            merged = spec.strategy(obj_v, db_v)
            if merged != db_v:
                setattr(
                    self.existing,
                    name,
                    merged,
                )
                updated.append(name)
        result = MergeResult.unnecessary()
        for name, o2o_spec in self.__registry__.one_to_one.items():
            o2o_result = o2o_spec.merge(
                self.existing, self.scrape, self.params
            )
            model_name = o2o_spec.merger.model.__name__
            if model_name in o2o_result.creates:
                field = self.model._meta.get_field(name)
                attname = getattr(field, "attname", f"{name}_id")
                setattr(
                    self.existing,
                    attname,
                    next(iter(o2o_result.creates[model_name])),
                )
            if o2o_result.update or o2o_result.create:
                updated.append(name)
            result |= o2o_result
        if updated or self.needs_update():
            result |= MergeResult.updated(
                self.model.__name__, self.existing.pk
            )
            updated += self.pre_update(updated)
            if updated:
                updated += auto_now_fields(self.model)
            self.existing.save(update_fields=updated)

        return result

    def create_new(self) -> tuple[M, MergeResult[Any]]:
        result = MergeResult.unnecessary()
        o2o_params: dict[str, Any] = {}
        for name, spec in self.__registry__.one_to_one.items():
            field = self.model._meta.get_field(name)
            attname = getattr(field, "attname", f"{name}_id")
            result |= spec.merge(None, self.scrape, self.params)
            model_name = spec.merger.model.__name__
            if model_name in result.creates:
                o2o_params[attname] = next(iter(result.creates[model_name]))
        db_obj = self.manager.create(
            **(
                {
                    name: self.transformed[name]
                    for name in self.__registry__.attr.keys()
                }
                | self._relation_params
                | o2o_params
            ),
        )
        result |= MergeResult.created(self.model.__name__, db_obj.pk)
        return db_obj, result

    def merge_one(self) -> tuple[MergeResult[Any], M | None]:
        """Merge the object's own attributes and then all of its related/child mergers, returning the combined result.

        When `atomic` is set, the caller runs this inside a single
        `transaction.atomic()` block, so the object and its whole related tree
        commit or roll back together.

        Returns:
            The result of the merge operation and the merged object
        """
        result = MergeResult.unnecessary()

        if self.existing is None:
            db_obj, result = self.create_new()
        else:
            result |= self.update_existing()
            db_obj = self.existing

        for rm in self.__registry__.related.values():
            result |= rm.merge(db_obj, self.scrape, self.params)

        return result, db_obj
