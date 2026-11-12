from __future__ import annotations

import functools
import logging
import operator
import typing
from abc import ABC, abstractmethod
from collections.abc import (
    Callable,
    Iterable,
    Mapping,
    Sequence,
)
from enum import Enum
from typing import (
    Any,
    cast,
    final,
    override,
)

from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db.models import (
    Field,
    ForeignObjectRel,
    Model,
    OneToOneRel,
    QuerySet,
)

from cl.corpus_importer.state.utils import MergeResult

from . import state as MergerState
from .lookup import KeyLookup, RelationLookup
from .parameters import (
    Create,
    RelatedParams,
    ThroughParameters,
    Update,
)
from .strategy import Strategy, overwrite

if typing.TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from .base import Merger

logger = logging.getLogger(__name__)

type Transformer[Scrape, Params, Transformed] = Callable[
    [Scrape, Params], Transformed
]


class MergerSpecification[Scrape, Params, Output](ABC):
    __slots__ = ("_name",)

    def __init__(self, /):
        self._name: str = ""

    def run_validation(
        self, merger: type[Merger[Scrape, Params, Any]]
    ) -> list[Exception]:
        """Runs validation for this spec against the given merger, returning any errors found."""
        try:
            f = merger.config.model._meta.get_field(self._name)
        except FieldDoesNotExist as e:
            return [e]
        if isinstance(f, GenericForeignKey):
            return [
                TypeError(
                    f"{self._name}: Generic foreign keys are not supported yet."
                )
            ]
        return self.validate(f)

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        """Validate this specification for the given field.

        Args:
            field: The field to validate this specification for.

        Returns:
            A list of errors encountered during validation. These will be surfaced after the merger is fully
            constructed and will prevent the `merge` method from being called.
        """
        return []

    def __set_name__(self, owner: type, name: str):
        from .base import Merger

        if not issubclass(owner, Merger):
            return
        self._name = name

    @abstractmethod
    def transform(self, scrape: Scrape, params: Params) -> Output: ...


class AttributeMerger[Scrape, Params, Transform](
    MergerSpecification[Scrape, Params, Transform]
):
    """An expression computing one model attribute at merge time.

    Instances are not built directly: start from `Scrape`, `Params`,
    `Ancestor`, `Constant` or `Fn` and chain attribute access, indexing and
    calls onto the result. Each step returns another expression rather than a
    value; nothing is evaluated until `transform` is called.

    Because attribute access is itself part of the expression language, a name
    that isn't defined on the class is never an `AttributeError` here; it
    becomes a deferred lookup that fails only when the merge runs.

    Attributes:
        strategy: How the computed value is reconciled with the value already
            in the DB. Set it with `WithStrategy`.
    """

    __slots__ = (
        "strategy",
        "_transform",
    )

    _transform: Transformer[Any, Any, Any]

    def __init__(self):
        """Create an expression using the `overwrite_if_present` strategy."""
        super().__init__()
        self.strategy: Strategy = overwrite

    def __getattr__(self, name: str) -> _AttrProxy | Any:
        """Build an expression reading an attribute of this one's value.

        Names defined on the class resolve to the expression's own attribute
        instead, so a scraped attribute called e.g. `strategy` or `transform`
        cannot be reached this way.

        Args:
            name: The attribute to read at merge time.

        Returns:
            The expression for the attribute, or this expression's own
            attribute when `name` is defined on the class.
        """
        for cls in self.__class__.__mro__:
            if hasattr(cls, name):
                return getattr(cls, name).__get__(self)

        # ABCs and other stuff inspect dunder attributes to function
        if name.startswith("__"):
            raise AttributeError(name)

        return _AttrProxy(self, name)

    def __getitem__(self, key: Any) -> _ItemProxy:
        """Build an expression indexing this one's value at merge time.

        Args:
            key: The index or key to look up. An expression is evaluated
                against the same scrape and params first; anything else is
                used as-is.

        Returns:
            The expression for the indexed value.
        """
        return _ItemProxy(self, key)

    def __call__(self, *args: Any, **kwargs: Any) -> _CallProxy:
        """Build an expression calling this one's value at merge time.

        Arguments that are expressions are evaluated against the same scrape
        and params first; all others are passed through as-is.

        Args:
            *args: Positional arguments for the call.
            **kwargs: Keyword arguments for the call.

        Returns:
            The expression for the call's result.
        """
        return _CallProxy(self, args, kwargs)

    @override
    @final
    def transform(self, scrape: Scrape, params: Params) -> Transform:
        """Evaluate this expression.

        Args:
            scrape: The scrape being merged.
            params: The params passed to the merger.

        Returns:
            The value of the expression for this scrape and params.
        """
        return self._transform(scrape, params)


class _AncestorProxy[M: Model](AttributeMerger):
    """Expression evaluating to the nearest ancestor of a given model type.

    Build it with `Ancestor`.
    """

    def __init__(self, model: type[M]):
        """Create an expression looking up an ancestor.

        Args:
            model: The model class of the ancestor to look up.
        """
        super().__init__()
        self._transform = functools.partial(_ancestor, model)


def _ancestor[M: Model](model: type[M], scrape: Any, params: Any) -> M:
    """Find the nearest parent of a given type among nested `RelatedParams`.

    Args:
        model: The model class of the parent to find.
        scrape: Unused; present so this can serve as a transform.
        params: The params of the merger being run.

    Returns:
        The nearest parent that is an instance of `model`.

    Raises:
        TypeError: If no parent of that type is in the chain, including when
            `params` is not a `RelatedParams` at all.
    """
    current = params
    while isinstance(current, RelatedParams):
        if isinstance(current.parent, model):
            return current.parent
        current = current.params
    raise TypeError(f"Unable to find model {model.__name__} in ancestor list")


class _ConstantProxy(AttributeMerger):
    """Expression evaluating to a fixed value.

    Build it with `Constant` or `Fn`.
    """

    __slots__ = ("_value",)

    def __init__(self, value: Any):
        """Create an expression evaluating to a fixed value.

        Args:
            value: The value to evaluate to. It is shared between every
                merge, so it should not be mutated.
        """
        super().__init__()
        self._transform = lambda s, p: value
        self._value = value


class _ScrapeProxy(AttributeMerger):
    """Expression evaluating to the scrape itself.

    Build it with `Scrape`.
    """

    def __init__(self):
        """Create an expression evaluating to the scrape."""
        super().__init__()
        self._transform = lambda s, p: s


class _ParamsProxy(AttributeMerger):
    """Expression evaluating to the merger's params.

    Build it with `Params`.
    """

    def __init__(self):
        """Create an expression evaluating to the params."""
        super().__init__()
        self._transform = lambda s, p: p


class _AttrProxy(AttributeMerger):
    """Expression reading an attribute of another expression's value.

    Chained attribute accesses collapse into a single dotted lookup. Built by
    attribute access on an expression.
    """

    __slots__ = ("_key", "_previous")

    def __init__(self, previous: AttributeMerger, key: str):
        """Create an expression reading an attribute.

        Args:
            previous: The expression whose value the attribute is read from.
            key: The name of the attribute to read.
        """
        super().__init__()
        if isinstance(previous, _AttrProxy):
            key = f"{previous._key}.{key}"
            previous = previous._previous
        self._key = key
        self._previous: AttributeMerger = previous
        getter = operator.attrgetter(key)
        match previous:
            case _ScrapeProxy():
                self._transform = lambda s, p: getter(s)
            case _ParamsProxy():
                self._transform = lambda s, p: getter(p)
            case _ConstantProxy():
                v = previous._value
                self._transform = lambda s, p: getter(v)
            case _:
                g = previous._transform
                self._transform = lambda s, p: getter(g(s, p))


class _ItemProxy(AttributeMerger):
    """Expression indexing another expression's value.

    Built by subscripting an expression.
    """

    def __init__(self, previous: AttributeMerger, key: AttributeMerger | Any):
        """Create an expression indexing a value.

        Args:
            previous: The expression whose value is indexed.
            key: The index or key to look up. An expression is evaluated at
                merge time; anything else is used as-is.
        """
        super().__init__()
        if isinstance(key, AttributeMerger):
            f = key._transform
            match previous:
                case _ScrapeProxy():
                    self._transform = lambda s, p: s[f(s, p)]
                case _ParamsProxy():
                    self._transform = lambda s, p: p[f(s, p)]
                case _ConstantProxy():
                    v = previous._value
                    self._transform = lambda s, p: v[f(s, p)]
                case _:
                    g = previous._transform
                    self._transform = lambda s, p: g(s, p)[f(s, p)]
        else:
            getter = operator.itemgetter(key)
            match previous:
                case _ScrapeProxy():
                    self._transform = lambda s, p: getter(s)
                case _ParamsProxy():
                    self._transform = lambda s, p: getter(p)
                case _ConstantProxy():
                    v = previous._value
                    self._transform = lambda s, p: getter(v)
                case _:
                    g = previous._transform
                    self._transform = lambda s, p: getter(g(s, p))


class _CallProxy(AttributeMerger):
    """Expression calling another expression's value.

    Built by calling an expression.
    """

    def __init__(
        self,
        previous: AttributeMerger,
        args: tuple[AttributeMerger | Any, ...],
        kwargs: Mapping[str, AttributeMerger | Any],
    ):
        """Create an expression calling a value.

        Arguments that are expressions are evaluated at merge time; anything
        else is passed through as-is.

        Args:
            previous: The expression whose value is called.
            args: Positional arguments for the call.
            kwargs: Keyword arguments for the call.
        """
        super().__init__()

        # Three cheers for unintuitive behavior! (late binding)
        def _make_transform(
            v: AttributeMerger | Any,
        ) -> Transformer[Any, Any, Any]:
            """Wrap an argument so expressions and plain values evaluate alike.

            Args:
                v: The argument to wrap.

            Returns:
                A transform evaluating to the argument's value.
            """
            if isinstance(v, AttributeMerger):
                return v._transform
            return lambda s, p: v

        arg_fns = tuple(_make_transform(arg) for arg in args)
        kwarg_fns = {k: _make_transform(kwarg) for k, kwarg in kwargs.items()}

        match previous:
            case _ConstantProxy():
                f = previous._value
                self._transform = lambda s, p: f(
                    *(a(s, p) for a in arg_fns),
                    **{k: v(s, p) for k, v in kwarg_fns.items()},
                )
            case _:
                f = previous._transform
                self._transform = lambda s, p: f(s, p)(
                    *(a(s, p) for a in arg_fns),
                    **{k: v(s, p) for k, v in kwarg_fns.items()},
                )


def Fn[F: Callable](f: F) -> F:
    """Wrap a callable so it can be invoked at merge time.

    Calling the result inside a merger definition builds an expression which
    invokes `f` when the merge runs, e.g.
    `Fn(parse_date)(Scrape(dict)["filed"])`.

    Args:
        f: The callable to invoke at merge time.

    Returns:
        An expression typed as `F` so calls to it type-check. It is not `f`:
        calling it returns another expression rather than `f`'s result, so it
        is only meaningful as (part of) a merger attribute.
    """
    # pyrefly: ignore[bad-return]
    return _ConstantProxy(f)


def Scrape[T](_: type[T]) -> T:
    """Start an expression from the scrape passed to the merger.

    For example, `Scrape(dict)["docket_number"]`.

    Args:
        _: The type of the scrape. It only informs the type checker; it is
            never instantiated or checked at runtime.

    Returns:
        An expression typed as `T` so chained accesses type-check. It is not
        a `T`: it has no value until the merge runs, so it is only meaningful
        as (part of) a merger attribute.
    """
    # pyrefly: ignore[bad-return]
    return _ScrapeProxy()


def Params[T](_: type[T]) -> T:
    """Start an expression from the params passed to the merger.

    For example, `Params(DocketParams).court_id`.

    Args:
        _: The type of the params. It only informs the type checker; it is
            never instantiated or checked at runtime.

    Returns:
        An expression typed as `T` so chained accesses type-check. It is not
        a `T`: it has no value until the merge runs, so it is only meaningful
        as (part of) a merger attribute.
    """
    # pyrefly: ignore[bad-return]
    return _ParamsProxy()


def Ancestor[M: Model](model: type[M]) -> M:
    """Start an expression from a parent this merger is nested under.

    For example, `Ancestor(Docket).court`. Only usable in mergers run as a
    relation of another merger; evaluation raises `TypeError` if no parent of
    type `model` exists.

    Args:
        model: The model class of the parent to use. The nearest parent of
            that type is chosen.

    Returns:
        An expression typed as `M` so chained accesses type-check. It is not
        a model instance: it has no value until the merge runs, so it is only
        meaningful as (part of) a merger attribute.
    """
    # pyrefly: ignore[bad-return]
    return _AncestorProxy(model)


def Constant[T](value: T) -> T:
    """Build an expression that always evaluates to the same value.

    Use it for attributes that don't depend on the scrape or params.

    Args:
        value: The value to evaluate to. The same object is shared by every
            merge, so it should not be mutable state.

    Returns:
        An expression typed as `T`. It is not `value` itself, so it is only
        meaningful as (part of) a merger attribute.
    """
    # pyrefly: ignore[bad-return]
    return _ConstantProxy(value)


def WithStrategy[T](specification: T, strategy: Strategy) -> T:
    """Set how an attribute expression's value is reconciled with the DB.

    This mutates `specification` rather than copying it, so an expression
    shared between attributes takes on the strategy everywhere it is used.

    Args:
        specification: The attribute expression to change.
        strategy: The strategy to use in place of the default
            `overwrite_if_present`.

    Returns:
        The same `specification` object that was passed in.

    Raises:
        TypeError: If `specification` is not an attribute expression.
    """
    if not isinstance(specification, AttributeMerger):
        raise TypeError(
            f"Specification must be an AttributeMerger. Found {type(specification)!r}"
        )
    specification.strategy = strategy
    return specification


class RelatedMerger[
    Scrape,
    Params,
    Transform,
    Child,
    RM: Model,
](
    MergerSpecification[Scrape, Params, Transform],
    ABC,
):
    __slots__ = "merger", "attribute", "after"

    def __init__(
        self,
        merger: type[Merger[Child, RelatedParams[Params], RM]],
        attribute: AttributeMerger[Scrape, Params, Transform],
        *,
        after: Iterable[str] = (),
    ):
        """
        Args:
            merger: The merger for the related objects.
            attribute: The expression computing the related scrape data.
            after: The names of the sibling relations that must be merged
                before this one.
        """
        super().__init__()
        self.merger: type[Merger[Child, RelatedParams[Params], RM]] = merger
        self.attribute: AttributeMerger[Scrape, Params, Transform] = attribute
        self.after: frozenset[str] = frozenset(after)

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.related_model:
            errors.append(
                TypeError(f"Field {self._name} is not a related field")
            )
        if (
            field.related_model is not None
            and field.related_model != self.merger.config.model
        ):
            if field.related_model == "self":
                errors.append(
                    TypeError(
                        f"{self._name}: Merging self references is not supported yet."
                    )
                )
            else:
                errors.append(
                    TypeError(
                        f"Field {self._name} is related to {field.related_model.__name__}, not {self.merger.config.model.__name__}"
                        # type: ignore[union-attr]
                    )
                )
        return errors

    @property
    def prefetch(self) -> list[str]:
        """The `prefetch_related` lookups, relative to the parent's model,
        loading everything that merging this relation looks for."""
        return [
            self._name,
            *[
                f"{self._name}__{path}"
                for path in self.merger.config.registry.prefetch
            ],
        ]

    @abstractmethod
    def merge(
        self, parent: RM | None, scrape: Scrape, params: Params
    ) -> MergeResult: ...

    @override
    def transform(self, scrape: Scrape, params: Params) -> Transform:
        return self.attribute.transform(scrape, params)


class OneToOneMerger[Scrape, Params, Child, RM: Model](
    RelatedMerger[
        Scrape,
        Params,
        Child | None,
        Child,
        RM,
    ]
):
    """Class encapsulating logic for merging a one-to-one relationship, in either direction."""

    __slots__: tuple[str, ...] = "forward", "parent_name"

    def __init__(
        self,
        merger: type[Merger[Child, RelatedParams[Params], RM]],
        attribute: AttributeMerger[Scrape, Params, Child | None],
        *,
        after: Iterable[str] = (),
    ):
        super().__init__(merger, attribute, after=after)
        self.forward: bool = True
        self.parent_name: str | None = None

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        """Validate the field and, along the way, learn which side of the relation it is. A reverse relation is a `OneToOneRel` rather than a `OneToOneField`, and carries the name of the child's own field."""
        errors = super().validate(field)
        if not field.one_to_one:
            errors.append(
                TypeError(f"{self._name}: Is not a one-to-one field")
            )
            return errors
        if isinstance(field, OneToOneRel):
            self.forward = False
            self.parent_name = field.field.name
        return errors

    def merge(
        self, parent: RM | None, scrape: Scrape, params: Params
    ) -> MergeResult:
        """Run the merge method on the appropriate inputs for the given relationship."""
        merger_input = self.transform(scrape, params)
        if merger_input is None:
            return MergeResult.unnecessary()

        if parent is None:
            if not self.forward:
                # A reverse relation is merged after its parent exists, so
                # there is nothing to hang the child off of without one.
                logger.error("%s: No parent model specified", self._name)
                return MergeResult.failed(self.merger.config.model.__name__)
            db_obj = None
        else:
            try:
                db_obj = cast(RM | None, getattr(parent, self._name))
            except ObjectDoesNotExist:
                # Unlike a forward one-to-one, an absent reverse relation
                # raises instead of returning None.
                db_obj = None

        return self.merger(
            merger_input,
            existing=Create if db_obj is None else Update(db_obj),
            params=RelatedParams(
                params, parent=parent, parent_name=self.parent_name
            ),
        ).merge()


def OneToOneRelation[Scrape, Params, Child, RM: Model](
    merger: type[Merger[Child, RelatedParams[Params], RM]],
    attribute: AttributeMerger[Scrape, Params, Child | None],
    *,
    after: Iterable[str] = (),
) -> Any:
    return OneToOneMerger(merger, attribute, after=after)


class ManyStrategy(Enum):
    """Enum specifying how to handle already-present values when merging n-to-many relationships."""

    APPEND = "append"
    """Leave set of existing values and add new values"""
    REPLACE = "replace"
    """Replace entire set of existing values with new values"""
    DISASSOCIATE = "disassociate"
    """Remove associations to values absent from the new data but keep the objects themselves in the DB"""


class NToManyMerger[Scrape, Params, Child, RM: Model](
    RelatedMerger[Scrape, Params, Sequence[Child], Child, RM],
    ABC,
):
    """Class encapsulating logic for merging an N-to-many relationship."""

    __slots__: tuple[str, ...] = ("strategy",)

    def __init__(
        self,
        merger: type[Merger[Child, RelatedParams[Params], RM]],
        attribute: AttributeMerger[Scrape, Params, Sequence[Child]],
        *,
        strategy: ManyStrategy = ManyStrategy.REPLACE,
        after: Iterable[str] = (),
    ):
        super().__init__(merger, attribute, after=after)
        self.strategy: ManyStrategy = strategy

    def _transform_result_and_manager(
        self, parent: RM | None, scrape: Scrape, params: Params
    ) -> tuple[Sequence[Child], MergeResult, RelatedManager[Any]]:
        related_manager: RelatedManager[Any] = getattr(parent, self._name)
        transformed = self.transform(scrape, params)
        if isinstance(transformed, (str, bytes)):
            return (
                [],
                MergeResult.failed(self.merger.config.model.__name__),
                related_manager,
            )
        return transformed, MergeResult.unnecessary(), related_manager

    def merge(
        self, parent: RM | None, scrape: Scrape, params: Params
    ) -> MergeResult:
        """Run the merge method on the appropriate inputs for the given relationship."""
        if parent is None:
            logger.error("Parent not provided for N to many merging")
            return MergeResult.failed(self.merger.config.model.__name__)

        transformed, result, related_manager = (
            self._transform_result_and_manager(parent, scrape, params)
        )

        if not transformed:
            return result

        related_params = RelatedParams(params, parent=parent)

        children = RelationLookup(self.merger, related_manager.all())
        child_mergers = [
            self.merger(
                child,
                params=related_params,
                manager=related_manager,
                siblings=children,
            )
            for child in transformed
        ]
        related_objects: list[RM] = []
        for child_merger in child_mergers:
            result |= child_merger.merge()
            if isinstance(state := child_merger.state, MergerState.Complete):
                related_objects.append(state.output)

        match self.strategy:
            case ManyStrategy.REPLACE:
                if len(related_objects) == len(child_mergers):
                    to_keep = {r.pk for r in related_objects}
                    if stale := {o.pk for o in children.existing()} - to_keep:
                        _ = related_manager.filter(pk__in=stale).delete()
            case ManyStrategy.DISASSOCIATE:
                related_manager.set(related_objects)
            # If we're using the `APPEND` strategy, we don't need to do anything special since the `RelatedManager`
            # handles everything for us
            case _:
                pass

        return result


class OneToManyMerger[Scrape, Params, Child, RM: Model](
    NToManyMerger[Scrape, Params, Child, RM]
):
    """Class encapsulating logic for merging a one-to-many relationship.

    More precisely: defines how to merge a collection of `B` models which have
    foreign keys pointing to a single `A` model (i.e. `DocketEntry` ->
    `Docket`).
    """

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.one_to_many:
            errors.append(
                TypeError(f"{self._name}: Is not a one-to-many field")
            )
        return errors


def OneToManyRelation[Scrape, Params, Child, RM: Model](
    merger: type[Merger[Child, RelatedParams[Params], RM]],
    attribute: AttributeMerger[Scrape, Params, Sequence[Child]],
    *,
    strategy: ManyStrategy = ManyStrategy.REPLACE,
    after: Iterable[str] = (),
) -> Any:
    return OneToManyMerger(merger, attribute, strategy=strategy, after=after)


class ManyToManyMerger[
    Scrape,
    Params,
    Transform,
    ThruM: Model,
    RM: Model,
](NToManyMerger[Scrape, Params, Transform, RM]):
    """Class encapsulating logic for merging a many-to-many relationship.

    A scrape whose transform yields no children is treated as a partial
    scrape: existing related objects and through rows are left untouched.
    """

    __slots__: tuple[str, ...] = (
        "through",
        "through_strategy",
    )

    def __init__(
        self,
        merger: type[Merger[Transform, RelatedParams[Params], RM]],
        attribute: AttributeMerger[Scrape, Params, Sequence[Transform]],
        through: type[Merger[Transform, ThroughParameters[Params], ThruM]]
        | None = None,
        *,
        strategy: ManyStrategy = ManyStrategy.REPLACE,
        through_strategy: ManyStrategy = ManyStrategy.REPLACE,
        after: Iterable[str] = (),
    ):
        super().__init__(merger, attribute, strategy=strategy, after=after)
        self.through: (
            type[Merger[Transform, ThroughParameters[Params], ThruM]] | None
        ) = through
        self.through_strategy: ManyStrategy = through_strategy

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.many_to_many:
            errors.append(
                TypeError(f"{self._name}: Is not a many-to-many field")
            )

        if self.through:
            if field.remote_field.through != self.through.config.model:  # type: ignore[union-attr]
                errors.append(
                    TypeError(
                        f"{self._name}: Model for through merger is {self.through.config.model.__name__} not {field.remote_field.through.__name__}"  # type: ignore[union-attr]
                    )
                )

            if field.remote_field.model != self.merger.config.model:  # type: ignore[union-attr]
                errors.append(
                    TypeError(
                        f"{self._name}: Model for source merger is {self.merger.config.model.__name__} not {field.remote_field.model.__name__}"  # type: ignore[union-attr]
                    )
                )

        return errors

    @property
    @override
    def prefetch(self) -> list[str]:
        if self.through is not None:
            # The related objects are looked up among every object of their
            # model rather than among those the parent already holds.
            return []
        return super().prefetch

    def merge(
        self, parent: RM | None, scrape: Scrape, params: Params
    ) -> MergeResult:
        """Run the merge method on the appropriate inputs for the given relationship."""
        if parent is None:
            logger.error("%s: No parent model specified", self._name)
            return MergeResult.failed(self.merger.config.model.__name__)
        if self.through is None:
            # If there's no `through` model, everything is functionally the same as `OneToMany`
            return super().merge(parent, scrape, params)

        transformed, result, related_manager = (
            self._transform_result_and_manager(parent, scrape, params)
        )

        if not transformed:
            return result

        related_params = RelatedParams(params, parent=parent)

        # We don't pass the manager, because it will automatically create `through` objects, which we don't want in
        # this case
        children = KeyLookup(self.merger)
        child_mergers = [
            self.merger(child, params=related_params, siblings=children)
            for child in transformed
        ]
        merged_children: list[tuple[Transform, RM]] = []
        children_to_keep: set[Any] = set()
        for child_merger in child_mergers:
            result |= child_merger.merge()
            match child_merger.state:
                case MergerState.Complete(state=state, output=output):
                    merged_children.append((state.scrape, output))
                    children_to_keep.add(output.pk)
                case MergerState.Failed(
                    state=MergerState.Update(instance=existing)
                ):
                    children_to_keep.add(existing.pk)
                case _:
                    pass

        # A failed merge can leave behind a row that its merger never identified:
        # invalid input and an ambiguous lookup both give up without finding the
        # existing row. Those rows aren't in the keep set, so a `REPLACE` prune has to be
        # skipped entirely rather than deleting data a later scrape could still match.
        all_children_merged = len(merged_children) == len(child_mergers)
        if self.strategy is ManyStrategy.REPLACE and all_children_merged:
            # Delete everything we didn't update or create along with associated objects
            _ = related_manager.exclude(pk__in=children_to_keep).delete()

        # Only through objects belonging to this parent are matched or
        # pruned; other parents' relationships are out of scope for this
        # merge.
        throughs = RelationLookup(
            self.through,
            cast(
                QuerySet[ThruM],
                self.through.config.model._default_manager.filter(
                    **{related_manager.source_field_name: parent}  # type: ignore[attr-defined]
                ),
            ),
        )
        through_mergers = [
            self.through(
                child_scrape,
                params=ThroughParameters(
                    params,
                    parent=parent,
                    source=parent,
                    source_name=related_manager.source_field_name,  # type: ignore[attr-defined]
                    target=child,
                    target_name=related_manager.target_field_name,  # type: ignore[attr-defined]
                ),
                siblings=throughs,
            )
            for child_scrape, child in merged_children
        ]
        through_objects: list[ThruM] = []
        for through_merger in through_mergers:
            result |= through_merger.merge()
            if isinstance(state := through_merger.state, MergerState.Complete):
                through_objects.append(state.output)

        # Through mergers exist only for children that merged successfully, so
        # a failed child's through row is never in the keep set. Pruning is
        # only safe when every child produced output.
        if (
            self.through_strategy is ManyStrategy.REPLACE
            and all_children_merged
            and len(through_objects) == len(through_mergers)
        ):
            to_keep = {t.pk for t in through_objects}
            if stale := {t.pk for t in throughs.existing()} - to_keep:
                _ = self.through.config.model._default_manager.filter(
                    pk__in=stale
                ).delete()

        return result


def ManyToManyRelation[Scrape, Params, Child, ThruM: Model, RM: Model](
    merger: type[Merger[Child, RelatedParams[Params], RM]],
    attribute: AttributeMerger[Scrape, Params, Sequence[Child]],
    through: type[Merger[Child, ThroughParameters[Params], ThruM]]
    | None = None,
    *,
    strategy: ManyStrategy = ManyStrategy.REPLACE,
    through_strategy: ManyStrategy = ManyStrategy.REPLACE,
    after: Iterable[str] = (),
) -> Any:
    return ManyToManyMerger(
        merger,
        attribute,
        through,
        strategy=strategy,
        through_strategy=through_strategy,
        after=after,
    )
