from __future__ import annotations

import logging
from collections.abc import (
    Callable,
    Iterable,
    Mapping,
    Sequence,
)
from dataclasses import dataclass, field
from functools import cache, cached_property
from graphlib import CycleError, TopologicalSorter
from itertools import chain
from typing import (
    Any,
    ClassVar,
    Final,
    cast,
    override,
)

from django.db.models import (
    Model,
    Prefetch,
    QuerySet,
)
from django.db.models.manager import Manager

from cl.corpus_importer.state.utils import MergeResult

from . import state as MergerState
from .lookup import Duplicate, KeyLookup, NaturalKey, SiblingLookup
from .parameters import (
    Create,
    Existing,
    Lookup,
    RelatedParams,
    ThroughParameters,
)
from .specifications import (
    AttributeMerger,
    ManyToManyMerger,
    MergerSpecification,
    OneToManyMerger,
    OneToOneMerger,
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


type AnyRelatedMerger[Scrape, Params] = (
    OneToOneMerger[Scrape, Params, Any, Model]
    | OneToManyMerger[Scrape, Params, Any, Model]
    | ManyToManyMerger[Scrape, Params, Model, Any, Any]
)


@dataclass(kw_only=True)
class MergerSpecRegistry[Scrape, Params]:
    """The specifications declared on a merger."""

    attr: dict[str, AttributeMerger[Scrape, Params, Any]] = field(
        default_factory=dict
    )
    one_to_one: dict[str, OneToOneMerger[Scrape, Params, Any, Model]] = field(
        default_factory=dict
    )
    one_to_many: dict[str, OneToManyMerger[Scrape, Params, Any, Model]] = (
        field(default_factory=dict)
    )
    many_to_many: dict[
        str, ManyToManyMerger[Scrape, Params, Model, Any, Any]
    ] = field(default_factory=dict)
    _transformers: dict[str, Callable[[Scrape, Params], Any]] = field(
        default_factory=dict
    )

    @cached_property
    def related(self) -> dict[str, AnyRelatedMerger[Scrape, Params]]:
        """Every relation spec, keyed by field name."""
        return self.one_to_one | self.one_to_many | self.many_to_many

    @cached_property
    def merge_order(self) -> list[AnyRelatedMerger[Scrape, Params]]:
        """The related specs in an order that satisfies every spec's `after`.

        :raises graphlib.CycleError: If the `after` declarations are circular.
        """
        related = self.related
        graph = {name: spec.after for name, spec in related.items()}
        return [
            related[name] for name in TopologicalSorter(graph).static_order()
        ]

    @cached_property
    def prefetch(self) -> tuple[Prefetch, ...]:
        """The `prefetch_related` lookups, relative to the merger's model, loading everything the mergers of its relations look for."""
        return tuple(
            path for spec in self.related.values() for path in spec.prefetch
        )

    def validate(
        self, merger: type[Merger[Scrape, Params, Any]]
    ) -> list[Exception]:
        """Run validation for every attached spec against the given merger.

        Used to defer running validation on base classes which may not have
        required properties defined yet.

        Validation is also the first point at which a one-to-one spec knows
        which side of the relation it is on, and where circular `after`
        declarations are reported.
        """
        errors = [
            e
            for spec in chain(self.attr.values(), self.related.values())
            for e in spec.run_validation(merger)
        ]

        unknown = [
            ValueError(f"{name}: Runs after unknown related spec {dep}")
            for name, spec in self.related.items()
            for dep in spec.after
            if dep not in self.related
        ]
        errors += unknown
        # Settling the order here keeps it off the first merge. An unknown
        # dependency has no spec to order, so there is nothing to settle.
        if not unknown:
            try:
                _ = self.merge_order
            except CycleError as e:
                errors.append(e)

        model_fields = merger.config.model._meta.get_fields()
        fields = {field.name: field for field in model_fields}

        for name in self.related.keys():
            attname = getattr(fields[name], "attname", None)
            if attname is not None and attname in self.attr:
                errors.append(
                    TypeError(
                        f"Cannot merge both {name} and {attname} on {merger.config.model.__name__}"
                    )
                )

        return errors

    def register(self, spec: MergerSpecification[Scrape, Params, Any]):
        """Add a spec under the name it was declared with."""
        match spec:
            case AttributeMerger():
                self.attr[spec._name] = spec
            case OneToOneMerger():
                self.one_to_one[spec._name] = spec
            case OneToManyMerger():
                self.one_to_many[spec._name] = spec
            case ManyToManyMerger():
                self.many_to_many[spec._name] = spec
            case _:
                logger.error(f"Unknown merger spec type: {spec!r}")
                return
        self._transformers[spec._name] = spec.transform

    def transform(self, scrape: Scrape, params: Params) -> dict[str, Any]:
        """Compute the value of every registered spec for a scrape."""
        return {k: v(scrape, params) for k, v in self._transformers.items()}


@dataclass(slots=True)
class MergerConfig[M: Model]:
    """Class-level settings determining a merger's behavior.

    :ivar model: The model the merger applies to.
    :ivar key: A natural key to use for looking up objects in the DB; used in
        the default `lookup` implementation.
    :ivar reads: Additionaly model fields to load. Useful for situations like
        preventing extra queries from custom `save` methods that inspect fields.
    :ivar registry: The specs declared on the merger. Filled in when the
        merger class is created, so it should not be passed.
    :ivar fields: The model fields loaded of an object read to be merged
        into; every other field is deferred. Filled in when the merger class
        is created, so it should not be passed.
    """

    model: Final[type[M]]
    key: Final[Iterable[str]] = ()
    reads: Final[Iterable[str]] = ()
    registry: MergerSpecRegistry[Any, Any] = field(
        default_factory=MergerSpecRegistry
    )
    fields: tuple[str, ...] = ()


class Merger[Scrape, Params, M: Model](MergerState.Machine[Scrape, Params, M]):
    """Base class for a merger which takes in `D` and merges it into `model`.

    The value computed for each declared spec is stored on the instance under
    the spec's name, unless the input failed validation.
    """

    config: ClassVar[MergerConfig[Model]]
    """Configurable information determining merger behavior."""

    def __init_subclass__(cls, abstract: bool = False) -> None:
        """Initialize a merger subclass.

        Args:
            abstract: Whether this merger is abstract and should not be instantiated/validated.
        """
        super().__init_subclass__()

        if abstract:
            return

        # We need this so that merger subclassing works like you'd expect.
        # Because we're efficient and don't check for specifications on every merge, we need to keep a cache. A
        # dictionary would be a great cache! Unfortunately, when you subclass, that dictionary is not reinitialized
        # so you need to copy it to avoid polluting your base class with your subclass' specs.
        registry: MergerSpecRegistry[Any, Any] = MergerSpecRegistry()

        for k in dir(cls):
            if isinstance(v := getattr(cls, k, None), MergerSpecification):
                registry.register(v)

        errors = registry.validate(cls)

        model = cls.config.model
        reads = tuple(
            dict.fromkeys(
                chain.from_iterable(
                    config.reads
                    for base in cls.__mro__
                    if (config := vars(base).get("config")) is not None
                )
            )
        )
        # Django reads a row's foreign keys to tie it to the objects it is
        # related to, so deferring one costs a query per row.
        foreign_keys = [
            f.attname for f in model._meta.concrete_fields if f.is_relation
        ]
        cls.config = MergerConfig(
            model,
            cls.config.key,
            reads,
            registry,
            tuple(
                dict.fromkeys(
                    chain(registry.attr, cls.config.key, reads, foreign_keys)
                )
            ),
        )

        if errors:
            raise TypeError(
                "Invalid merger configuration for {}:\n{}".format(
                    cls.config.model.__name__,
                    "\n".join(f"- {repr(e)}" for e in errors),
                )
            )

    def initial_state(
        self, scrape: Scrape, params: Params, existing: Existing[M]
    ) -> MergerState.AnyState[Scrape, Params, M]:
        """Generate the initial state for this merger based on its inputs and overrides.

        Args:
            scrape: The scraped data
            params: Any supplemental parameters
            existing: User-supplied override for lookup behavior

        Returns:
            The state the merger starts in.
        """
        if not self.validator(scrape):
            logger.error(
                f"Merger {self.__class__.__name__} received invalid input."
            )
            return MergerState.Failed(
                None,
                "Validator returned false",
                MergeResult.failed(self.config.model.__name__),
            )

        # Relations the merger fills in itself rather than leaving to a spec: a
        # `through` model's two ends, or the foreign key a reverse one-to-one
        # child points back at its parent with. They are set on create, kept on
        # update, and narrow the lookup for an existing object.
        # It's hacky but it works.
        relation_params: dict[str, Model]
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
        else:
            relation_params = {}

        if existing is Lookup:
            return MergerState.Lookup(scrape, params, relation_params)

        if existing is Create:
            return MergerState.Create(scrape, params, relation_params)

        return MergerState.Update(
            scrape, params, relation_params, existing.instance
        )

    def __init__(
        self,
        scrape: Scrape,
        *,
        params: Params,
        existing: Existing[M] = Lookup,
        manager: Manager[M] | None = None,
        siblings: SiblingLookup[M] | None = None,
    ):
        """Create an object to track the merge operation on the specified data.

        Args:
            scrape: The scraped data to transform.
            params: Parameters passed to the merger.
            existing: Whether to look the object up, create it, or merge into a known one.
            manager: The manager to use for lookups and creation of objects. Defaults to the model's default manager.
            siblings: The lookup shared with the mergers created alongside
                this one, all of which must be created before any is merged.

        Attributes:
            manager: The manager to use for lookups and creation of objects.
            siblings: The lookup that finds the object to merge into.
        """
        super().__init__(self.initial_state(scrape, params, existing))

        if (
            not isinstance(self.state, MergerState.Failed)
            or self.state.state is not None
        ):
            vars(self).update(self.config.registry.transform(scrape, params))

        if manager is None:
            manager = cast(Manager[M], self.config.model._default_manager)
        self.manager: Manager[M] = manager

        if siblings is None:
            siblings = KeyLookup(type(self))
        self.siblings: SiblingLookup[M] = siblings
        if isinstance(self.state, MergerState.Lookup):
            siblings.claim(self.natural_key(self.state), self)

    @staticmethod
    def validator(scrape: Scrape) -> bool:
        """Validate the input data before attempting a merge operation.

        Args:
            scrape: Input data to the merge

        Returns:
            True if the input is valid and the merge operation can proceed. False if the merge operation should be canceled.
        """
        # TODO: This is temporary. In the future, validation should be very detailed about failures
        return True

    def natural_key(
        self, state: MergerState.Lookup[Scrape, Params, M]
    ) -> NaturalKey:
        """The natural key this merger looks its object up by."""
        attributes = {name: getattr(self, name) for name in self.config.key}
        relations = state.relation_params
        return NaturalKey(
            filters={**attributes, **relations},
            attnames=(*attributes, *[f"{name}_id" for name in relations]),
            values=tuple(
                [str(value) for value in attributes.values()]
                + [str(obj.pk) for obj in relations.values()]
            ),
        )

    @classmethod
    def loading(cls, objects: QuerySet[M]) -> QuerySet[M]:
        """Have a query load what merging its objects takes and no more: the fields this merger uses, and everything the mergers of its relations look for.

        The related objects come without their other fields too, and so does
        anything queried through the relation they were loaded into. Deleting
        through such a relation hands the deletion signals objects with
        fields missing; delete through the model's manager instead.

        Args:
            objects: A query for objects of this merger's model.

        Returns:
            The narrowed query.
        """
        return objects.only(*cls.config.fields).prefetch_related(
            *cls.config.registry.prefetch
        )

    @property
    def stored(self) -> QuerySet[M]:
        """The objects this merger can merge into, loaded with only the fields it uses. A lookup that evaluates its own query should build it from this rather than from `manager`."""
        return self.manager.only(*self.config.fields)

    def _key_query(
        self, state: MergerState.Lookup[Scrape, Params, M]
    ) -> QuerySet[M]:
        """The objects matching this merger's natural key."""
        return self.stored.filter(**self.natural_key(state).filters)

    def pre_update(self, updated_fields: list[str]) -> list[str]:
        """Called before an updated instance is saved. Useful for setting attributes that are dependent on the result of the merge operation.

        Args:
            updated_fields: The fields that were updated.

        Returns:
            A list of additional attribute names that should be updated.
        """
        return []

    def needs_update(self) -> bool:
        """Whether to take the update path even when no attribute changed. Useful for re-triggering downstream processing (e.g. a re-download) driven by the merge result's updates.

        Returns:
            True to force the update path.
        """
        return False

    @override
    def lookup(
        self, state: MergerState.Lookup[Scrape, Params, M]
    ) -> MergerState.LookupOutput[Scrape, Params, M]:
        candidates = self.siblings.candidates(self.natural_key(state), self)
        if candidates is Duplicate:
            model_name = self.config.model.__name__
            logger.error(
                "Multiple scraped instances with same natural key for model %s",
                model_name,
            )
            return state.failed(
                "Multiple scraped instances with same natural key",
                MergeResult.failed(model_name),
            )
        return state.resolve(candidates)

    @override
    def resolve(
        self, state: MergerState.Resolve[Scrape, Params, M]
    ) -> MergerState.ResolveOutput[Scrape, Params, M]:
        results: Sequence[M]
        if isinstance(state.candidates, QuerySet):
            if state.candidates._result_cache is None:
                qs = state.candidates.only(*self.config.fields)[:2]
            else:
                qs = state.candidates

            results = list(qs)
        else:
            results = state.candidates

        if len(results) == 0:
            return state.create()

        if len(results) == 1:
            return state.update(results[0])

        logger.error(
            "Merger %s found multiple objects; skipping merge.",
            self.__class__.__name__,
        )
        return state.failed(
            "Ambiguous query results",
            MergeResult.failed(self.config.model.__name__),
        )

    def merge(self) -> MergeResult:
        """Merge scraped data into the DB."""
        return self.run().result

    def _attributes(self, relation_params: Mapping[str, Model]) -> dict:
        """The model field values this merger computed or was handed."""
        return {
            name: getattr(self, name) for name in self.config.registry.attr
        } | dict(relation_params)

    @override
    def update(
        self, state: MergerState.Update[Scrape, Params, M]
    ) -> MergerState.UpdateOutput[Scrape, Params, M]:
        obj = cast(
            M, self.config.model(**self._attributes(state.relation_params))
        )

        updated: list[str] = []
        for name, spec in self.config.registry.attr.items():
            obj_v = getattr(obj, name)
            db_v = getattr(state.instance, name)
            merged = spec.strategy(obj_v, db_v)
            if merged != db_v:
                setattr(
                    state.instance,
                    name,
                    merged,
                )
                updated.append(name)
        result = MergeResult.unnecessary()
        for name, o2o_spec in self.config.registry.one_to_one.items():
            if not o2o_spec.forward:
                continue
            o2o_result = o2o_spec.merge(
                state.instance, state.scrape, state.params
            )
            model_name = o2o_spec.merger.config.model.__name__
            if model_name in o2o_result.creates:
                field = self.config.model._meta.get_field(name)
                attname = getattr(field, "attname", f"{name}_id")
                setattr(
                    state.instance,
                    attname,
                    next(iter(o2o_result.creates[model_name])),
                )
            if o2o_result.update or o2o_result.create:
                updated.append(name)
            result |= o2o_result
        if updated or self.needs_update():
            result |= MergeResult.updated(
                self.config.model.__name__, state.instance.pk
            )
            updated += self.pre_update(updated)
            if updated:
                updated += auto_now_fields(self.config.model)
            state.instance.save(update_fields=updated)

        if self.config.registry.related:
            return state.children(state.instance, result)
        return state.complete(state.instance, result)

    @override
    def create(
        self, state: MergerState.Create[Scrape, Params, M]
    ) -> MergerState.CreateOutput[Scrape, Params, M]:
        result = MergeResult.unnecessary()
        o2o_params: dict[str, Any] = {}
        for name, spec in self.config.registry.one_to_one.items():
            if not spec.forward:
                continue
            field = self.config.model._meta.get_field(name)
            attname = getattr(field, "attname", f"{name}_id")
            result |= spec.merge(None, state.scrape, state.params)
            model_name = spec.merger.config.model.__name__
            if model_name in result.creates:
                o2o_params[attname] = next(iter(result.creates[model_name]))
        db_obj = self.manager.create(
            **(self._attributes(state.relation_params) | o2o_params),
        )
        result |= MergeResult.created(self.config.model.__name__, db_obj.pk)

        if self.config.registry.related:
            return state.children(db_obj, result)
        return state.complete(db_obj, result)

    @override
    def children(
        self, state: MergerState.Children[Scrape, Params, M]
    ) -> MergerState.ChildrenOutput[Scrape, Params, M]:
        result = state.result
        for rm in self.config.registry.merge_order:
            # A forward one-to-one is merged before its parent is saved, since
            # the parent stores the key.
            if isinstance(rm, OneToOneMerger) and rm.forward:
                continue
            result |= rm.merge(state.parent, state.scrape, state.params)

        return state.complete(state.parent, result)

    @override
    def complete(
        self, state: MergerState.Complete[Scrape, Params, M]
    ) -> MergerState.CompleteOutput[Scrape, Params, M]:
        logger.info("Yay done")
        return state

    @override
    def failed(
        self, state: MergerState.Failed[Scrape, Params, M]
    ) -> MergerState.FailedOutput[Scrape, Params, M]:
        logger.error(":(")
        return state
