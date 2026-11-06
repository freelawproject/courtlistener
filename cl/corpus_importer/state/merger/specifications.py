from __future__ import annotations

import logging
import typing
from abc import ABC, abstractmethod
from collections.abc import (
    Callable,
    Sequence,
)
from enum import Enum
from typing import (
    Any,
    cast,
)

from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db.models import (
    Field,
    ForeignObjectRel,
    Model,
    OneToOneRel,
)

from cl.corpus_importer.state.utils import MergeResult

from .parameters import (
    RelatedParams,
    ThroughParameters,
)
from .strategy import overwrite_if_present

if typing.TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

    from .base import Merger

logger = logging.getLogger(__name__)


class MergerSpecification[ScrapeType, ParamType, OutputType]:
    __slots__: tuple[str, ...] = "name", "transform", "default"

    def __init__(
        self,
        *,
        transform: Callable[[ScrapeType, ParamType], OutputType] | None = None,
        default: OutputType,
    ):
        self.transform: Callable[[ScrapeType, ParamType], OutputType] = (
            transform or self._default_transform
        )
        self.default: OutputType = default
        self.name: str = ""

    def run_validation(
        self, merger: type[Merger[Any, Any, Any]]
    ) -> list[Exception]:
        """Runs validation for this spec against the given merger, returning any errors found."""
        try:
            f = merger.model._meta.get_field(self.name)
        except FieldDoesNotExist as e:
            return [e]
        if isinstance(f, GenericForeignKey):
            return [
                TypeError(
                    f"{self.name}: Generic foreign keys are not supported yet."
                )
            ]
        return self.validate(f)

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        """Validate this specification for the given field.

        :param field: The field to validate this specification for.

        :return: A list of errors encountered during validation. These will be surfaced after the merger is fully
        constructed and will prevent the `merge` method from being called."""
        return []

    def __set_name__(self, owner: type, name: str):
        from .base import Merger

        if not issubclass(owner, Merger):
            return
        self.name = name
        owner.__registry__.register(self)

    def _default_transform(
        self, scrape: ScrapeType, params: ParamType
    ) -> OutputType:
        if params is None:
            return self.default
        if isinstance(params, dict):
            return params.get(self.name, self.default)
        return getattr(params, self.name, self.default)


class AttributeMerger[ScrapeType, ParamType, TransformType](
    MergerSpecification[ScrapeType, ParamType, TransformType | None]
):
    """Class encapsulating logic for merging a single attribute from a scrape into a DB object.

    :param transform: Defines how to get the DB value from the scrape data
    :param strategy: How to behave when data is present in the scrape and DB. Defaults to overwriting the DB value
        only when the scraped value is present (not `None`), so a partial scrape won't overwrite existing data."""

    __slots__: tuple[str, ...] = ("strategy",)

    def __init__(
        self,
        transform: Callable[[ScrapeType, ParamType], TransformType]
        | None = None,
        strategy: Callable[
            [TransformType | None, TransformType | None],
            TransformType | None,
        ] = overwrite_if_present,
        *,
        default: TransformType | None = None,
    ):
        super().__init__(transform=transform, default=default)
        self.strategy: Callable[
            [TransformType | None, TransformType | None],
            TransformType | None,
        ] = strategy


def Attribute[TransformType](
    transform: Callable[[Any, Any], TransformType] | None = None,
    strategy: Callable[
        [Any, Any], TransformType | None
    ] = overwrite_if_present,
    *,
    default: TransformType | None = None,
) -> Any:
    return AttributeMerger(transform, strategy, default=default)


class RelatedMerger[
    ScrapeType,
    ParamType,
    ChildType,
    OutputType,
    RM: Model,
](
    MergerSpecification[ScrapeType, ParamType, OutputType],
    ABC,
):
    __slots__ = ("merger",)

    def __init__(
        self,
        merger: type[Merger[ChildType, RelatedParams[ParamType], RM]],
        transform: Callable[[ScrapeType, ParamType], OutputType] | None = None,
        *,
        default: OutputType,
    ):
        super().__init__(transform=transform, default=default)
        self.merger: type[Merger[ChildType, RelatedParams[ParamType], RM]] = (
            merger
        )

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.related_model:
            errors.append(
                TypeError(f"Field {self.name} is not a related field")
            )
        if (
            field.related_model is not None
            and field.related_model != self.merger.model
        ):
            if field.related_model == "self":
                errors.append(
                    TypeError(
                        f"{self.name}: Merging self references is not supported yet."
                    )
                )
            else:
                errors.append(
                    TypeError(
                        f"Field {self.name} is related to {field.related_model.__name__}, not {self.merger.model.__name__}"
                        # type: ignore[union-attr]
                    )
                )
        return errors

    @abstractmethod
    def merge(
        self, parent: RM | None, scrape: ScrapeType, params: ParamType
    ) -> MergeResult[Any]: ...


class OneToOneMerger[ScrapeType, ParamType, ChildType, RM: Model](
    RelatedMerger[
        ScrapeType,
        ParamType,
        ChildType,
        ChildType | None,
        RM,
    ]
):
    """Class encapsulating logic for merging a one-to-one relationship, in
    either direction."""

    __slots__: tuple[str, ...] = "forward", "parent_name"

    def __init__(
        self,
        merger: type[Merger[ChildType, RelatedParams[ParamType], RM]],
        transform: Callable[[ScrapeType, ParamType], ChildType | None]
        | None = None,
    ):
        super().__init__(merger=merger, transform=transform, default=None)
        self.forward: bool = True
        self.parent_name: str | None = None

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        """Validate the field and, along the way, learn which side of the
        relation it is. A reverse relation is a `OneToOneRel` rather than a
        `OneToOneField`, and carries the name of the child's own field."""
        errors = super().validate(field)
        if not field.one_to_one:
            errors.append(TypeError(f"{self.name}: Is not a one-to-one field"))
            return errors
        if isinstance(field, OneToOneRel):
            self.forward = False
            self.parent_name = field.field.name
        return errors

    def merge(
        self, parent: RM | None, scrape: ScrapeType, params: ParamType
    ) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship."""
        merger_input = self.transform(scrape, params)
        if merger_input is None:
            return MergeResult.unnecessary()

        if parent is None:
            if not self.forward:
                # A reverse relation is merged after its parent exists, so
                # there is nothing to hang the child off of without one.
                logger.error("%s: No parent model specified", self.name)
                return MergeResult.failed(self.merger.model.__name__)
            db_obj = None
        else:
            try:
                db_obj = cast(RM | None, getattr(parent, self.name))
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


def OneToOneRelation[ParamType, ChildType, RM: Model](
    merger: type[Merger[ChildType, RelatedParams[ParamType], RM]],
    transform: Callable[..., ChildType | None] | None = None,
) -> Any:
    return OneToOneMerger(merger, transform)


class ManyStrategy(Enum):
    """Enum specifying how to handle already-present values when merging n-to-many relationships."""

    APPEND = "append"
    """Leave set of existing values and add new values"""
    REPLACE = "replace"
    """Replace entire set of existing values with new values"""
    DISASSOCIATE = "disassociate"
    """Remove associations to values absent from the new data but keep the objects themselves in the DB"""


class NToManyMerger[ScrapeType, ParamType, ChildType, RM: Model](
    RelatedMerger[ScrapeType, ParamType, ChildType, Sequence[ChildType], RM],
    ABC,
):
    """Class encapsulating logic for merging an N-to-many relationship."""

    __slots__: tuple[str, ...] = ("strategy",)

    def __init__(
        self,
        merger: type[Merger[ChildType, RelatedParams[ParamType], RM]],
        transform: Callable[[ScrapeType, ParamType], Sequence[ChildType]]
        | None = None,
        *,
        strategy: ManyStrategy = ManyStrategy.REPLACE,
    ):
        super().__init__(merger=merger, transform=transform, default=[])
        self.strategy: ManyStrategy = strategy

    def _transform_result_and_manager(
        self, parent: RM | None, scrape: ScrapeType, params: ParamType
    ) -> tuple[Sequence[ChildType], MergeResult[Any], RelatedManager[Any]]:
        related_manager: RelatedManager[Any] = getattr(parent, self.name)
        transformed = self.transform(scrape, params)
        if isinstance(transformed, (str, bytes)):
            return (
                [],
                MergeResult.failed(self.merger.model.__name__),
                related_manager,
            )
        return transformed, MergeResult.unnecessary(), related_manager

    def merge(
        self, parent: RM | None, scrape: ScrapeType, params: ParamType
    ) -> MergeResult[Any]:
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


class OneToManyMerger[ScrapeType, ParamType, ChildType, RM: Model](
    NToManyMerger[ScrapeType, ParamType, ChildType, RM]
):
    """Class encapsulating logic for merging a one-to-many relationship. More precisely: defines how to merge a
    collection of `B` models which have foreign keys pointing to a single `A` model (i.e. `DocketEntry` -> `Docket`)."""

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.one_to_many:
            errors.append(
                TypeError(f"{self.name}: Is not a one-to-many field")
            )
        return errors


def OneToManyRelation[ParamType, ChildType, RM: Model](
    merger: type[Merger[ChildType, RelatedParams[ParamType], RM]],
    transform: Callable[..., Sequence[ChildType]] | None = None,
    *,
    strategy: ManyStrategy = ManyStrategy.REPLACE,
) -> Any:
    return OneToManyMerger(merger, transform, strategy=strategy)


class ManyToManyMerger[
    ScrapeType,
    TransformType,
    ThruM: Model,
    RM: Model,
    ParamType,
](NToManyMerger[ScrapeType, ParamType, TransformType, RM]):
    """Class encapsulating logic for merging a many-to-many relationship.

    A scrape whose transform yields no children is treated as a partial
    scrape: existing related objects and through rows are left untouched."""

    __slots__: tuple[str, ...] = (
        "through",
        "through_strategy",
    )

    def __init__(
        self,
        merger: type[Merger[TransformType, RelatedParams[ParamType], RM]],
        through: type[
            Merger[TransformType, ThroughParameters[ParamType], ThruM]
        ]
        | None = None,
        transform: Callable[[ScrapeType, ParamType], Sequence[TransformType]]
        | None = None,
        *,
        strategy: ManyStrategy = ManyStrategy.REPLACE,
        through_strategy: ManyStrategy = ManyStrategy.REPLACE,
    ):
        super().__init__(merger, transform, strategy=strategy)
        self.through: (
            type[Merger[TransformType, ThroughParameters[ParamType], ThruM]]
            | None
        ) = through
        self.through_strategy: ManyStrategy = through_strategy

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.many_to_many:
            errors.append(
                TypeError(f"{self.name}: Is not a many-to-many field")
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
        self, parent: RM | None, scrape: ScrapeType, params: ParamType
    ) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship."""
        if parent is None:
            logger.error("%s: No parent model specified", self.name)
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
            Merger[TransformType, RelatedParams[ParamType], RM]
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


def ManyToManyRelation[ParamType, ChildType, ThruM: Model, RM: Model](
    merger: type[Merger[ChildType, RelatedParams[ParamType], RM]],
    through: type[Merger[ChildType, ThroughParameters[ParamType], ThruM]]
    | None = None,
    transform: Callable[[Any, Any], Sequence[ChildType]] | None = None,
    *,
    strategy: ManyStrategy = ManyStrategy.REPLACE,
    through_strategy: ManyStrategy = ManyStrategy.REPLACE,
) -> Any:
    return ManyToManyMerger(
        merger,
        through,
        transform,
        strategy=strategy,
        through_strategy=through_strategy,
    )
