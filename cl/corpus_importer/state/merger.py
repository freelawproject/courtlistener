import logging
import typing
from abc import ABC, abstractmethod
from collections.abc import (
    Callable,
    Iterable,
    MutableMapping,
    Sequence,
)
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Self,
    cast,
)

from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.db.models import (
    Field,
    ForeignObjectRel,
    Model,
    QuerySet,
)
from django.db.models.manager import Manager

from cl.corpus_importer.state.utils import MergeResult

if typing.TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager

logger = logging.getLogger(__name__)


def overwrite[T](scrape: T | None, db: T | None) -> T | None:
    """Merge strategy that always overwrites the existing value with the scraped value."""

    return scrape


def overwrite_if_present[T](scrape: T | None, db: T | None) -> T | None:
    """Merge strategy that overwrites the existing value only when the scraped
    value is present (i.e. not `None`), otherwise keeping the DB value.

    This is the default strategy so that a partial scrape -- one that is missing
    a field it didn't manage to extract -- does not clobber good data already in
    the DB. Note that "present" means `not None`: a scraped empty string or `0`
    is treated as a real value and will overwrite the DB value. Use
    `OverwriteExisting` if `None` should be written, or `OverwriteConditionally`
    for finer-grained control."""

    return db if scrape is None else scrape


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
        self, merger: "type[Merger[Any, Any, Any]]"
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


@dataclass
class RelatedParams[ParamType]:
    """Wrapper for passing parameters to a related object."""

    params: ParamType
    parent: Model = field(kw_only=True)


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
        merger: "type[Merger[ChildType, RelatedParams[ParamType], RM]]",
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
                        f"Field {self.name} is related to {field.related_model.__name__}, not {self.merger.model.__name__}"  # type: ignore[union-attr]
                    )
                )
        return errors

    @abstractmethod
    def merge(
        self, parent: RM, scrape: ScrapeType, params: ParamType
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
    """Class encapsulating logic for merging a one-to-one relationship."""

    def __init__(
        self,
        merger: "type[Merger[ChildType, RelatedParams[ParamType], RM]]",
        transform: Callable[[ScrapeType, ParamType], ChildType | None]
        | None = None,
    ):
        super().__init__(merger=merger, transform=transform, default=None)

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.one_to_one:
            errors.append(TypeError(f"{self.name}: Is not a one-to-one field"))
        return errors

    def merge(
        self, parent: RM, scrape: ScrapeType, params: ParamType
    ) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship."""
        merger_input = self.transform(scrape, params)
        if merger_input is None:
            return MergeResult.unnecessary()

        related_params = RelatedParams(params, parent=parent)

        db_obj = cast(RM | None, getattr(parent, self.name))
        result = self.merger(
            merger_input, existing=db_obj, params=related_params
        ).merge()
        if db_obj is None:
            model = self.merger.model
            model_name = model.__name__
            if model_name in result.creates:
                db_obj_pk = next(iter(result.creates[model_name]))
                field = parent._meta.get_field(self.name)
                attname = getattr(field, "attname", f"{self.name}_id")
                setattr(parent, attname, db_obj_pk)
                parent.save(update_fields=[attname])
        return result


def OneToOneRelation[ParamType, ChildType, RM: Model](
    merger: "type[Merger[ChildType, RelatedParams[ParamType], RM]]",
    transform: Callable[..., ChildType | None] | None = None,
) -> Any:
    return OneToOneMerger(merger, transform)


class ManyStrategy(Enum):
    """Enum specifying how to handle already-present values when merging n-to-many relationships."""

    APPEND = "append"
    """Leave set of existing values and add new values"""
    REPLACE = "replace"
    """Replace entire set of existing values with new values"""


class NToManyMerger[ScrapeType, ParamType, ChildType, RM: Model](
    RelatedMerger[ScrapeType, ParamType, ChildType, Sequence[ChildType], RM],
    ABC,
):
    """Class encapsulating logic for merging an N-to-many relationship."""

    __slots__: tuple[str, ...] = ("strategy",)

    def __init__(
        self,
        merger: "type[Merger[ChildType, RelatedParams[ParamType], RM]]",
        transform: Callable[[ScrapeType, ParamType], Sequence[ChildType]]
        | None = None,
        *,
        strategy: ManyStrategy = ManyStrategy.REPLACE,
    ):
        super().__init__(merger=merger, transform=transform, default=[])
        self.strategy: ManyStrategy = strategy

    def _transform_result_and_manager(
        self, parent: RM, scrape: ScrapeType, params: ParamType
    ) -> "tuple[Sequence[ChildType], MergeResult[Any], RelatedManager[Any]]":
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
        self, parent: RM, scrape: ScrapeType, params: ParamType
    ) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship."""
        transformed, result, related_manager = (
            self._transform_result_and_manager(parent, scrape, params)
        )

        if not transformed:
            return result

        related_params = RelatedParams(params, parent=parent)

        related_objects: list[RM] = []
        for child in transformed:
            related_merge = self.merger(
                child, manager=related_manager, params=related_params
            )
            result |= related_merge.merge()
            if related_merge.out is None:
                continue
            related_objects.append(related_merge.out)

        match self.strategy:
            case ManyStrategy.APPEND:
                related_manager.add(*related_objects)
            case ManyStrategy.REPLACE:
                _ = related_manager.exclude(
                    pk__in=[r.pk for r in related_objects]
                ).delete()
                related_manager.add(*related_objects)

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
    merger: "type[Merger[ChildType, RelatedParams[ParamType], RM]]",
    transform: Callable[..., Sequence[ChildType]] | None = None,
    *,
    strategy: ManyStrategy = ManyStrategy.REPLACE,
) -> Any:
    return OneToManyMerger(merger, transform, strategy=strategy)


@dataclass
class ThroughParameters[ParamType](RelatedParams[ParamType]):
    """Wrapper for passing parameters to a `through` model.

    :ivar source: The source object of the relationship
    :ivar target: The target object of the relationship
    :ivar params: The parameters passed by the user to the merger"""

    source: Model = field(kw_only=True)
    source_name: str = field(kw_only=True)
    target: Model = field(kw_only=True)
    target_name: str = field(kw_only=True)
    params: ParamType


class ManyToManyMerger[
    ScrapeType,
    TransformType,
    ThruM: Model,
    RM: Model,
    ParamType,
](NToManyMerger[ScrapeType, ParamType, TransformType, RM]):
    """Class encapsulating logic for merging a many-to-many relationship."""

    __slots__: tuple[str, ...] = (
        "through",
        "through_strategy",
    )

    def __init__(
        self,
        merger: "type[Merger[TransformType, RelatedParams[ParamType], RM]]",
        through: "type[Merger[TransformType, ThroughParameters[ParamType], ThruM]] | None" = None,
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
            if field.remote_field is None:
                return errors + [
                    TypeError(
                        f"{self.name}: No through model specified on source field"
                    )
                ]

            if field.remote_field.through != self.through.model:  # type: ignore[union-attr]
                errors.append(
                    TypeError(
                        f"{self.name}: Model for through merger is {self.through.model.__name__} not {field.remote_field.through.__name__}"  # type: ignore[union-attr]
                    )
                )

            if field.remote_field.model != self.merger.model:
                errors.append(
                    TypeError(
                        f"{self.name}: Model for source merger is {self.merger.model.__name__} not {field.remote_field.model.__name__}"
                    )
                )

        return errors

    def merge(
        self, parent: RM, scrape: ScrapeType, params: ParamType
    ) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship."""
        if self.through is None:
            # If there's no `through` model, everything is functionally the same as `OneToMany`
            return super().merge(parent, scrape, params)

        transformed, result, related_manager = (
            self._transform_result_and_manager(parent, scrape, params)
        )

        if not transformed:
            return result

        related_params = RelatedParams(params, parent=parent)

        child_mergers: list[
            Merger[TransformType, RelatedParams[ParamType], RM]
        ] = []
        related_objects: list[tuple[TransformType, RM]] = []
        for child in transformed:
            # We don't pass the manager, because it will automatically create `through` objects, which we don't want in
            # this case
            child_merger = self.merger(child, params=related_params)
            child_mergers.append(child_merger)
            result |= child_merger.merge()
            if child_merger.out is None:
                continue
            related_objects.append((child, child_merger.out))

        if self.strategy is ManyStrategy.REPLACE:
            # Delete everything we didn't update or create along with associated objects
            to_keep = {r.pk for _, r in related_objects} | {
                m.existing.pk for m in child_mergers if m.existing
            }
            _ = related_manager.exclude(pk__in=to_keep).delete()

        through_mergers: list[
            Merger[TransformType, ThroughParameters[ParamType], ThruM]
        ] = []
        through_objects: list[ThruM] = []
        for related_transform, related_object in related_objects:
            through_merger = self.through(
                related_transform,
                params=ThroughParameters(
                    params,
                    parent=parent,
                    source=parent,
                    source_name=related_manager.source_field_name,  # type: ignore[attr-defined]
                    target=related_object,
                    target_name=related_manager.target_field_name,  # type: ignore[attr-defined]
                ),
                existing=None,
            )
            through_mergers.append(through_merger)
            result |= through_merger.merge()
            if through_merger.out is None:
                continue
            through_objects.append(through_merger.out)

        if self.through_strategy is ManyStrategy.REPLACE:
            to_keep = {t.pk for t in through_objects} | {
                m.existing.pk for m in through_mergers if m.existing
            }
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
    merger: "type[Merger[ChildType, RelatedParams[ParamType], RM]]",
    through: "type[Merger[ChildType, ThroughParameters[ParamType], ThruM]] | None" = None,
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
    ):
        self.related: dict[
            str, RelatedMerger[ScrapeType, ParamType, Any, Any, Model]
        ] = related or {}
        self.attr: dict[str, AttributeMerger[ScrapeType, ParamType, Any]] = (
            attr or {}
        )

    def __copy__(self) -> Self:
        return self.__class__(related=self.related, attr=self.attr)

    def __or__(self, other: Self) -> Self:
        return self.__class__(
            related=self.related | other.related, attr=self.attr | other.attr
        )

    def validate(
        self, merger: "type[Merger[ScrapeType, ParamType, Any]]"
    ) -> list[Exception]:
        """Run validation for every attached spec against the given merger. Used to defer running validation on base
        classes which may not have required properties defined yet."""
        errors = []

        for related_spec in self.related.values():
            errors += related_spec.run_validation(merger)

        for attr_spec in self.attr.values():
            errors += attr_spec.run_validation(merger)

        return errors

    def update(self, other: Self):
        self.related.update(other.related)
        self.attr.update(other.attr)

    def register(self, spec: MergerSpecification[ScrapeType, ParamType, Any]):
        match spec:
            case AttributeMerger():
                self.attr[spec.name] = spec
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
    """Base class for a merger which takes in `D` and merges it into `model`. Subclasses should generally not be
    instantiated; methods and attributes should be accessed directly from the class.

    :cvar model: The model this merger applies to.
    :cvar atomic: Whether to wrap the entire merge operation -- the object's own attributes *and* all related/child
        mergers -- in a single `transaction.atomic()` block, so the whole tree commits together or rolls back together
        if an exception is raised. Nested mergers that set their own `atomic` value simply create savepoints within
        this block.
    :cvar key: A natural key to use for looking up objects in the DB; used in the default `get_existing` implementation.
    :cvar errors: A list of errors encountered during validation of this merger. These will be surfaced after the merger
        is fully constructed and will prevent the `merge` method from being called.

    :ivar scrape: Data from scrape with no modifications
    :ivar params: Parameters passed to the merger
    :ivar transformed: Data from scrape after being run through all the transforms for attribute and related mergers
    :ivar existing: A matching object in the DB or `None` if not found. Initialized lazily
    :ivar result: Stores the result of the attempted merge operation. Initialized to `None` and updated when the
        merge attempt completes. If the input data is invalid, the result will instead be set to `MergeResult.failed`
    :ivar out: The object written to the DB or `None` if the merge failed. Initialized as `None` and updated after
        the merge attempt completes"""

    model: ClassVar[type[Model]]
    atomic: ClassVar[bool] = False
    key: ClassVar[Iterable[str]] = []
    errors: ClassVar[list[Exception]]
    __registry__: ClassVar[MergerSpecRegistry[Any, Any]]

    def __init_subclass__(cls, abstract: bool = False) -> None:
        """:param abstract: Whether this merger is abstract and should not be instantiated/validated."""

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

    @staticmethod
    def validate(scrape: ScrapeType) -> bool:
        """Validate the input data before attempting a merge operation

        :param scrape: Input data to the merge
        :return: True if the input is valid and the merge operation can proceed. False if the merge operation should be
            canceled."""
        return True

    def __init__(
        self,
        scrape: ScrapeType,
        *,
        params: ParamType,
        existing: M | None = None,
        manager: Manager[M] | None = None,
    ):
        """Create an object to track the merge operation on the specified data.

        :param scrape: The scraped data to transform. Parameter values are passed as kwargs.
        :param existing: Optional existing object to override the lookup in `get_existing`.
        :param manager: The manager to use for lookups and creation of objects. Defaults to the model's default manager."""
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
            if valid
            else {}
        )

        # It's hacky but it works
        self._through_params: dict[str, Model] = (
            {
                params.source_name: params.source,
                params.target_name: params.target,
            }
            if isinstance(params, ThroughParameters)
            else {}
        )

        if manager is None:
            manager = cast(Manager[M], self.model._default_manager)
        self.manager: Manager[M] = manager

        self.existing: M | None = existing

    def after(self) -> None:
        """Run extra processes after the merge operation completes or fails."""
        ...

    def query(self) -> QuerySet[M]:
        """Constructs a queryset to find an existing object in the DB, using the natural key defined by `cls.key`.

        :return: The queryset to find the object."""
        return self.manager.filter(
            **{name: self.transformed[name] for name in self.key},
        )

    def merge(self) -> MergeResult[Any]:
        """Merge scraped data into the DB."""
        if self.result is not None:
            return self.result
        if self.existing is None:
            try:
                self.existing = (
                    self.query().filter(**self._through_params).get()
                )
            except self.model.MultipleObjectsReturned:  # type: ignore[attr-defined]
                logger.error(
                    "Merger %s found multiple objects; skipping merge.",
                    self.__class__.__name__,
                )
                self.result = MergeResult.failed(self.model.__name__)
                return self.result
            except self.manager.model.DoesNotExist:  # type: ignore[attr-defined]
                self.existing = None

        if self.atomic:
            with transaction.atomic():
                result, out_obj = self.merge_one()
        else:
            result, out_obj = self.merge_one()
        self.result = result
        self.out = out_obj
        self.after()
        return result

    def build_object(self) -> M:
        """Build the object to be merged into the DB based on `self.transformed`"""
        return cast(
            M,
            self.model(
                **{
                    name: self.transformed[name]
                    for name in self.__registry__.attr.keys()
                },
            ),
        )

    def update_existing(self, obj: M) -> list[str]:
        """Merge `obj` into `self.existing` in-place and return the names of the updated fields. Does not execute
        related mergers."""

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
        if updated:
            self.existing.save(update_fields=updated)

        return updated

    def merge_one(self) -> tuple[MergeResult[Any], M | None]:
        """Merge the object's own attributes and then all of its related/child
        mergers, returning the combined result.

        When `atomic` is set, the caller runs this inside a single
        `transaction.atomic()` block, so the object and its whole related tree
        commit or roll back together.

        :return: The result of the merge operation and the merged object"""
        result = MergeResult.unnecessary()

        if self.existing is None:
            db_obj = self.manager.create(
                **(
                    {
                        name: self.transformed[name]
                        for name in self.__registry__.attr.keys()
                    }
                    | self._through_params
                ),
            )
            result = MergeResult.created(self.model.__name__, db_obj.pk)
        else:
            obj = self.build_object()
            if self.update_existing(obj):
                result = MergeResult.updated(
                    self.model.__name__, self.existing.pk
                )
            db_obj = self.existing

        for rm in self.__registry__.related.values():
            result |= rm.merge(db_obj, self.scrape, self.params)

        return result, db_obj
