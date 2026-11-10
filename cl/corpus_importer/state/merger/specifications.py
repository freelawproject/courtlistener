from __future__ import annotations

import functools
import logging
import operator
import typing
from abc import ABC, abstractmethod
from collections.abc import (
    Callable,
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
)
from typing_extensions import Sentinel

from cl.corpus_importer.state.utils import MergeResult

from .parameters import (
    RelatedParams,
    ThroughParameters,
)
from .strategy import Strategy, overwrite_if_present

if typing.TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from .base import Merger

logger = logging.getLogger(__name__)

type Transformer[Scrape, Params, Transformed] = Callable[
    [Scrape, Params], Transformed
]

Absent = Sentinel("Absent")


class MergerSpecification[Scrape, Params, Output](ABC):
    __slots__ = ("_name",)

    def __init__(self, /):
        self._name: str = ""

    def run_validation(
        self, merger: type[Merger[Scrape, Params, Any]]
    ) -> list[Exception]:
        """Runs validation for this spec against the given merger, returning any errors found."""
        try:
            f = merger.model._meta.get_field(self._name)
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
        owner.__registry__.register(self)

    @abstractmethod
    def transform(self, scrape: Scrape, params: Params) -> Output: ...


class AttributeMerger[Scrape, Params, Transform](
    MergerSpecification[Scrape, Params, Transform]
):
    __slots__ = (
        "strategy",
        "_transform",
    )

    _transform: Transformer[Any, Any, Any]

    def __init__(self):
        super().__init__()
        self.strategy: Strategy = overwrite_if_present

    def __getattr__(self, name: str) -> _AttrProxy | Any:
        for cls in self.__class__.__mro__:
            if hasattr(cls, name):
                return getattr(cls, name).__get__(self)

        # ABCs and other stuff inspect dunder attributes to function
        if name.startswith("__"):
            raise AttributeError(name)

        return _AttrProxy(self, name)

    def __getitem__(self, key: Any) -> _ItemProxy:
        return _ItemProxy(self, key)

    def __call__(self, *args: Any, **kwargs: Any) -> _CallProxy:
        return _CallProxy(self, args, kwargs)

    @override
    @final
    def transform(self, scrape: Any, params: Any) -> Any:
        return self._transform(scrape, params)


class _AncestorProxy[M: Model](AttributeMerger):
    def __init__(self, model: type[M]):
        super().__init__()
        self._transform = functools.partial(_ancestor, model)


def _ancestor[M: Model](model: type[M], scrape: Any, params: Any) -> M:
    current = params
    while isinstance(current, RelatedParams):
        if isinstance(current.parent, model):
            return current.parent
        current = current.params
    raise TypeError(f"Unable to find model {model.__name__} in ancestor list")


class _ConstantProxy(AttributeMerger):
    __slots__ = ("_value",)

    def __init__(self, value: Any):
        super().__init__()
        self._transform = lambda s, p: value
        self._value = value


class _ScrapeProxy(AttributeMerger):
    def __init__(self):
        super().__init__()
        self._transform = lambda s, p: s


class _ParamsProxy(AttributeMerger):
    def __init__(self):
        super().__init__()
        self._transform = lambda s, p: p


class _AttrProxy(AttributeMerger):
    __slots__ = ("_key", "_previous")

    def __init__(self, previous: AttributeMerger, key: str):
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
    def __init__(self, previous: AttributeMerger, key: AttributeMerger | Any):
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
    def __init__(
        self,
        previous: AttributeMerger,
        args: tuple[AttributeMerger | Any, ...],
        kwargs: Mapping[str, AttributeMerger | Any],
    ):
        super().__init__()

        # Three cheers for unintuitive behavior! (late binding)
        def _make_transform(
            v: AttributeMerger | Any,
        ) -> Transformer[Any, Any, Any]:
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
    # pyrefly: ignore[bad-return]
    return _ConstantProxy(f)


def Scrape[T](_: type[T]) -> T:
    # pyrefly: ignore[bad-return]
    return _ScrapeProxy()


def Params[T](_: type[T]) -> T:
    # pyrefly: ignore[bad-return]
    return _ParamsProxy()


def Ancestor[M: Model](model: type[M]) -> M:
    # pyrefly: ignore[bad-return]
    return _AncestorProxy(model)


def Constant[T](value: T) -> T:
    # pyrefly: ignore[bad-return]
    return _ConstantProxy(value)


def WithStrategy[T](specification: T, strategy: Strategy) -> T:
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
    __slots__ = "merger", "attribute"

    def __init__(
        self,
        merger: type[Merger[Child, RelatedParams[Params], RM]],
        attribute: AttributeMerger[Scrape, Params, Transform],
    ):
        super().__init__()
        self.merger: type[Merger[Child, RelatedParams[Params], RM]] = merger
        self.attribute: AttributeMerger[Scrape, Params, Transform] = attribute

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.related_model:
            errors.append(
                TypeError(f"Field {self._name} is not a related field")
            )
        if (
            field.related_model is not None
            and field.related_model != self.merger.model
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
                        f"Field {self._name} is related to {field.related_model.__name__}, not {self.merger.model.__name__}"
                        # type: ignore[union-attr]
                    )
                )
        return errors

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
    ):
        super().__init__(merger, attribute)
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
                return MergeResult.failed(self.merger.model.__name__)
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
            existing=db_obj,
            params=RelatedParams(
                params, parent=parent, parent_name=self.parent_name
            ),
        ).merge()


def OneToOneRelation[Scrape, Params, Child, RM: Model](
    merger: type[Merger[Child, RelatedParams[Params], RM]],
    attribute: AttributeMerger[Scrape, Params, Child | None],
) -> Any:
    return OneToOneMerger(merger, attribute)


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
    ):
        super().__init__(merger, attribute)
        self.strategy: ManyStrategy = strategy

    def _transform_result_and_manager(
        self, parent: RM | None, scrape: Scrape, params: Params
    ) -> tuple[Sequence[Child], MergeResult, RelatedManager[Any]]:
        related_manager: RelatedManager[Any] = getattr(parent, self._name)
        transformed = self.transform(scrape, params)
        if isinstance(transformed, (str, bytes)):
            return (
                [],
                MergeResult.failed(self.merger.model.__name__),
                related_manager,
            )
        return transformed, MergeResult.unnecessary(), related_manager

    def merge(
        self, parent: RM | None, scrape: Scrape, params: Params
    ) -> MergeResult:
        """Run the merge method on the appropriate inputs for the given relationship."""
        if parent is None:
            logger.error("Parent not provided for N to many merging")
            return MergeResult.failed(self.merger.model.__name__)

        transformed, result, related_manager = (
            self._transform_result_and_manager(parent, scrape, params)
        )

        if not transformed:
            return result

        related_params = RelatedParams(params, parent=parent)

        init_result, child_mergers = self.merger.init_many(
            transformed, params=related_params, manager=related_manager
        )
        result |= init_result
        related_objects: list[RM] = []
        for child_merger in child_mergers:
            result |= child_merger.merge()
            if child_merger.out is None:
                continue
            related_objects.append(child_merger.out)

        match self.strategy:
            case ManyStrategy.REPLACE:
                if all(m.out is not None for m in child_mergers):
                    to_keep = {r.pk for r in related_objects}
                    _ = related_manager.exclude(pk__in=to_keep).delete()
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
) -> Any:
    return OneToManyMerger(merger, attribute, strategy=strategy)


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
    ):
        super().__init__(merger, attribute, strategy=strategy)
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
            if field.remote_field.through != self.through.model:  # type: ignore[union-attr]
                errors.append(
                    TypeError(
                        f"{self.name}: Model for through merger is {self.through.model.__name__} not {field.remote_field.through.__name__}"  # type: ignore[union-attr]
                    )
                )

            if field.remote_field.model != self.merger.model:  # type: ignore[union-attr]
                errors.append(
                    TypeError(
                        f"{self.name}: Model for source merger is {self.merger.model.__name__} not {field.remote_field.model.__name__}"  # type: ignore[union-attr]
                    )
                )

        return errors

    def merge(
        self, parent: RM | None, scrape: Scrape, params: Params
    ) -> MergeResult:
        """Run the merge method on the appropriate inputs for the given relationship."""
        if parent is None:
            logger.error("%s: No parent model specified", self._name)
            return MergeResult.failed(self.merger.model.__name__)
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
        init_result, child_mergers = self.merger.init_many(
            transformed, params=related_params
        )
        result |= init_result
        mergers_with_output: list[
            Merger[Transform, RelatedParams[Params], RM]
        ] = []
        children_to_keep: set[Any] = set()
        for child_merger in child_mergers:
            result |= child_merger.merge()
            if child_merger.out is None:
                if child_merger.existing is not None:
                    children_to_keep.add(child_merger.existing.pk)
            else:
                mergers_with_output.append(child_merger)
                children_to_keep.add(child_merger.out.pk)

        # A failed merge can leave behind a row that its merger never identified:
        # invalid input and an ambiguous lookup both give up without setting
        # `existing`. Those rows aren't in the keep set, so a `REPLACE` prune has to be
        # skipped entirely rather than deleting data a later scrape could still match.
        all_children_merged = all(m.out is not None for m in child_mergers)
        if self.strategy is ManyStrategy.REPLACE and all_children_merged:
            # Delete everything we didn't update or create along with associated objects
            _ = related_manager.exclude(pk__in=children_to_keep).delete()

        through_init_result, through_mergers = self.through.init_many(
            [m.scrape for m in mergers_with_output],
            params=[
                ThroughParameters(
                    params,
                    parent=parent,
                    source=parent,
                    source_name=related_manager.source_field_name,  # type: ignore[attr-defined]
                    target=m.out,  # type: ignore[arg-type]
                    target_name=related_manager.target_field_name,  # type: ignore[attr-defined]
                )
                for m in mergers_with_output
            ],
        )
        result |= through_init_result
        through_objects: list[ThruM] = []
        for through_merger in through_mergers:
            result |= through_merger.merge()
            if through_merger.out is None:
                continue
            through_objects.append(through_merger.out)

        # Through mergers exist only for children that merged successfully, so
        # a failed child's through row is never in the keep set. Pruning is
        # only safe when every child produced output.
        if (
            self.through_strategy is ManyStrategy.REPLACE
            and all_children_merged
            and all(m.out is not None for m in through_mergers)
        ):
            to_keep = {t.pk for t in through_objects}
            # Only prune through objects belonging to this parent; other
            # parents' relationships are out of scope for this merge.
            _ = (
                self.through.model._default_manager.filter(
                    **{related_manager.source_field_name: parent}  # type: ignore[attr-defined]
                )
                .exclude(pk__in=to_keep)
                .delete()
            )

        return result


def ManyToManyRelation[Scrape, Params, Child, ThruM: Model, RM: Model](
    merger: type[Merger[Child, RelatedParams[Params], RM]],
    attribute: AttributeMerger[Scrape, Params, Sequence[Child]],
    through: type[Merger[Child, ThroughParameters[Params], ThruM]]
    | None = None,
    *,
    strategy: ManyStrategy = ManyStrategy.REPLACE,
    through_strategy: ManyStrategy = ManyStrategy.REPLACE,
) -> Any:
    return ManyToManyMerger(
        merger,
        attribute,
        through,
        strategy=strategy,
        through_strategy=through_strategy,
    )
