"""Declarative mergers that write scraped data into Django models."""

from __future__ import annotations

import logging
from collections.abc import (
    Iterable,
    Mapping,
)
from dataclasses import dataclass, field
from functools import cache, cached_property
from itertools import chain
from typing import (
    Any,
    ClassVar,
    Final,
    cast,
    final,
    override,
)

from django.db.models import (
    Model,
    Prefetch,
    QuerySet,
)
from django.db.models.manager import Manager
from graphlib import CycleError, TopologicalSorter

from cl.corpus_importer.state.utils import MergeResult

from . import state as MergerState
from .match import (
    BoundMatch,
    Key,
    Match,
    MatchGroup,
    ambiguous_text,
    failure_text,
)
from .parameters import (
    Create,
    Existing,
    Lookup,
    RelatedParams,
    ThroughParameters,
)
from .pool import Global, Pool
from .specifications import (
    AttributeMerger,
    ManyToManyMerger,
    MergerSpecification,
    OneToManyMerger,
    OneToOneMerger,
    Transformer,
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
    """A merger's specifications, by field name, grouped by kind."""

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
    _transformers: dict[str, Transformer[Scrape, Params, Any, Any]] = field(
        default_factory=dict
    )
    _deferred_transformers: dict[
        str, Transformer[Scrape, Params, Any, Any]
    ] = field(default_factory=dict)

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

    def register(self, spec: MergerSpecification[Scrape, Params, Any]) -> None:
        """Add a specification under its name, by kind; unknown kinds are logged."""
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
                logger.error("Unknown merger spec type: %r", spec)
                return
        if spec._db_fields:
            self._deferred_transformers[spec._name] = spec.transform
        else:
            self._transformers[spec._name] = spec.transform

    def transform[M: Model](
        self, scrape: Scrape, params: Params, database: None
    ) -> dict[str, Any]:
        """Get every specification's transformed value, by field name."""
        return {
            k: v(scrape, params, database)
            for k, v in self._transformers.items()
        }

    def deferred_transform[M: Model](
        self, scrape: Scrape, params: Params, database: M
    ) -> dict[str, Any]:
        """Get the value of every specification that reads the database, by field name, given the object being merged into."""
        return {
            k: v(scrape, params, database)
            for k, v in self._deferred_transformers.items()
        }

    def all(
        self,
    ) -> dict[
        str,
        AttributeMerger[Scrape, Params, Any]
        | ManyToManyMerger[Scrape, Params, Model, Any, Any]
        | OneToManyMerger[Scrape, Params, Any, Model]
        | OneToOneMerger[Scrape, Params, Any, Model],
    ]:
        """All the specifications stored in this registry."""
        return (
            self.attr | self.one_to_one | self.one_to_many | self.many_to_many
        )


@dataclass(slots=True)
class MergerConfig[M: Model]:
    """Class-level settings determining a merger's behavior.

    :ivar model: The model the merger applies to.
    :ivar reads: Additionaly model fields to load. Useful for situations like
        preventing extra queries from custom `save` methods that inspect fields.
    :ivar registry: The specs declared on the merger. Filled in when the
        merger class is created, so it should not be passed.
    :ivar fields: The model fields loaded of an object read to be merged
        into; every other field is deferred. Filled in when the merger class
        is created, so it should not be passed.
    """

    model: Final[type[M]]
    reads: Final[tuple[str, ...]] = ()
    registry: MergerSpecRegistry[Any, Any] = field(
        default_factory=MergerSpecRegistry
    )
    fields: tuple[str, ...] = field(init=False, default=())

    def loading[QModel: Model](
        self, objects: QuerySet[QModel]
    ) -> QuerySet[QModel]:
        """Have a query load only the fields this merger and the mergers of its relations use.

        Args:
            objects: A query for objects of this merger's model.

        Returns:
            The narrowed query.
        """
        return objects.only(*self.fields).prefetch_related(
            *self.registry.prefetch
        )

    @classmethod
    def inherit(
        cls,
        parent: type[Merger],
        registry: MergerSpecRegistry,
        columns: frozenset[str],
    ) -> MergerConfig:
        """Build a config for a subclass of ``parent`` using ``registry``.

        The subclass reads every field read by any of its mergers in the MRO.

        Args:
            parent: The merger class the config is for, or its base.
            registry: The specs declared on the merger.
            columns: The model fields the merger's match reads from stored
                rows, which are loaded with the fields its specs use.

        Returns:
            The config, with the fields to load worked out from the specs,
            reads and match columns.
        """
        config = MergerConfig(
            parent.config.model,
            reads=tuple(
                {
                    read
                    for base in parent.__mro__
                    if issubclass(base, Merger)
                    for read in base.config.reads
                }
            ),
            registry=registry,
        )
        config.fields = tuple(
            {
                *registry.attr,
                *config.reads,
                *columns,
                *(f for m in registry.all().values() for f in m._db_fields),
                *(
                    f.attname
                    for f in config.model._meta.concrete_fields
                    if f.is_relation
                ),
            }
        )
        return config


class Merger[Scrape, Params, M: Model](MergerState.Machine[Scrape, Params, M]):
    """Base class for a merger which takes in `D` and merges it into `model`.

    The value computed for each declared spec is stored on the instance under
    the spec's name, unless the input failed validation.

    A spec that reads the database has, until `update` runs, the value it
    would have with nothing stored, so `lookup` can match on what was scraped.
    """

    config: ClassVar[MergerConfig[Model]] = MergerConfig(Model)
    """Configurable information determining merger behavior."""

    pool: ClassVar[Pool | None] = None
    """Which stored rows the merger can match. Without one, the merger is matched in the pool of the relation it is merged through, or in `Global` when it has no parent."""

    match: ClassVar[Match] = Match(Key())
    """How the merger picks the stored row it merges into. The default `Key()` has no terms of its own, so it only separates rows by the merger's relation params."""

    _bound_match: ClassVar[BoundMatch]
    """`match` checked against this merger class. Set when the class is created."""

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

        # Binding the match reads the merger's model and specs from its config,
        # so a config is in place first and then completed with the columns
        # the match reads.
        cls.config = MergerConfig.inherit(cls, registry, frozenset())
        try:
            cls._bound_match = cls.match.bind(cls, cls.pool)
        except ExceptionGroup as problems:
            errors.extend(problems.exceptions)
        else:
            if cls.pool is not None:
                errors.extend(cls.pool_errors(cls.pool))
            cls.config = MergerConfig.inherit(
                cls, registry, cls._bound_match.columns
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
                "Merger %s received invalid input.", self.__class__.__name__
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
        group: MatchGroup[M] | None = None,
    ):
        """Create an object to track the merge operation on the specified data.

        Args:
            scrape: The scraped data to transform.
            params: Parameters passed to the merger.
            existing: Whether to look the object up, create it, or merge into a known one.
            manager: The manager to use for creation of objects. Defaults to the model's default manager.
            group: The match group shared with the mergers created alongside
                this one, all of which must be created before any is merged.
                A merger that looks its object up joins it. Without one, the
                merger builds a group of its own when it first looks.

        Attributes:
            manager: The manager to use for creation of objects.
            group: The match group that finds the object to merge into.
        """
        super().__init__(self.initial_state(scrape, params, existing))

        if (
            not isinstance(self.state, MergerState.Failed)
            or self.state.state is not None
        ):
            vars(self).update(
                self.config.registry.transform(scrape, params, None)
            )

        if manager is None:
            manager = cast(Manager[M], self.config.model._default_manager)
        self.manager: Manager[M] = manager

        self.group: MatchGroup[M] | None = group
        if group is not None and isinstance(self.state, MergerState.Lookup):
            group.join(self, self.state)

    @final
    def populate_from_db(
        self, state: MergerState.Update[Scrape, Params, M]
    ) -> None:
        """Compute the fields that read the database from the object being merged into, replacing any value read before it was found.

        Args:
            state: The update the merger is carrying out.
        """
        vars(self).update(
            self.config.registry.deferred_transform(
                state.scrape, state.params, state.instance
            )
        )

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

    @classmethod
    def pool_errors(cls, pool: Pool) -> list[Exception]:
        """Check this merger's match against the pool its rows are read from.

        Args:
            pool: The pool the merger is matched in.

        Returns:
            One error for each tier that cannot be queried in `pool`. A merger
            that overrides `lookup` never matches by its `match`, so it has
            none.
        """
        if cls.lookup is not Merger.lookup:
            return []
        return cls._bound_match.check_pool(pool)

    @override
    def lookup(
        self, state: MergerState.Lookup[Scrape, Params, M]
    ) -> MergerState.LookupOutput[Scrape, Params, M]:
        """Find the object to merge into by this merger's `match` in its `pool`.

        A merger created without a group has no siblings, so it is matched on
        its own in a group built here, in the merger's declared pool or
        `Global`.

        Returns:
            The state the merger moves to: creating a row, updating the row
            it matched, or failed.

        Raises:
            TypeError: If the match cannot be queried in the pool.
        """
        if self.group is None:
            self.group = MatchGroup.build(
                type(self),
                type(self).pool or Global(),
                relation=None,
                params=state.params,
            )
            self.group.join(self, state)
        return self.group.verdict(self, state)

    def found(
        self,
        state: MergerState.Lookup[Scrape, Params, M],
        rows: Iterable[M],
    ) -> MergerState.LookupOutput[Scrape, Params, M]:
        """Turn the rows a lookup found into the merger's verdict.

        For a merger that overrides `lookup` with a query of its own, such as
        a root merger finding its object by RECAP's rules.

        Args:
            state: The merger's state.
            rows: The rows the object to merge into can only be one of. The
                caller decides what is loaded of them and caps the read: a
                query that has not been evaluated is read in full, so it
                should be sliced to two rows and loaded with
                `only(*config.fields)`. An evaluated queryset costs nothing
                to read.

        Returns:
            The state the merger moves to: creating a row if there are none,
            updating the one there is, or failed if there are two or more,
            which is ambiguous.
        """
        found = list(rows)
        match found:
            case []:
                return state.create()
            case [row]:
                return state.update(row)
            case _:
                text = failure_text(
                    type(self),
                    ambiguous_text(self.config.model, len(found), 1),
                )
                logger.error("%s", text)
                return state.failed(
                    text, MergeResult.failed(self.config.model.__name__)
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
        self.populate_from_db(state)

        updated: list[str] = []
        for name in self.config.registry.attr:
            obj_v = getattr(self, name)
            db_v = getattr(state.instance, name)
            if obj_v != db_v:
                setattr(
                    state.instance,
                    name,
                    obj_v,
                )
                updated.append(name)
        result = MergeResult.unnecessary()
        for name, o2o_spec in self.config.registry.one_to_one.items():
            if not o2o_spec.forward:
                continue
            o2o_result = o2o_spec.merge(
                state.instance, getattr(self, name), state.params
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

        return state.save(state.instance, updated, result)

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
            result |= spec.merge(None, getattr(self, name), state.params)
            model_name = spec.merger.config.model.__name__
            if model_name in result.creates:
                o2o_params[attname] = next(iter(result.creates[model_name]))

        return state.save(
            self._attributes(state.relation_params) | o2o_params, result
        )

    @override
    def save(
        self, state: MergerState.Save[Scrape, Params, M]
    ) -> MergerState.SaveOutput[Scrape, Params, M]:
        result = state.result
        match state.operation:
            case MergerState.ModelCreate(fields):
                instance = self.manager.create(**fields)
                result |= MergeResult.created(
                    instance.__class__.__name__, instance.pk
                )
            case MergerState.ModelUpdate(instance, fields, force):
                if fields:
                    instance.save(
                        update_fields=(
                            *fields,
                            *auto_now_fields(self.config.model),
                        )
                    )
                if fields or force:
                    result |= MergeResult.updated(
                        instance.__class__.__name__, instance.pk
                    )

        if self.config.registry.related:
            return state.children(instance, result)
        return state.complete(instance, result)

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
            result |= rm.merge(
                state.parent, getattr(self, rm._name), state.params
            )

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
