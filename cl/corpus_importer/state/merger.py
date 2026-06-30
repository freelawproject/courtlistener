import logging
import typing
from abc import ABC, abstractmethod
from collections.abc import (
    Callable,
    Iterable,
    MutableMapping,
    Sequence,
)
from typing import (
    Any,
    ClassVar,
    Concatenate,
    Self,
    cast,
)

from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.db.models import Field, ForeignObjectRel, Model
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


def _default_transform[D, T](d: D, value: T | None = None) -> T | None:
    return value


class MergerSpecification[ScrapeType, TransformType, MergeType, DefaultType]:
    __slots__ = "name", "_transform", "default", "param"

    def __init__(
        self,
        *,
        transform: Callable[Concatenate[ScrapeType, ...], TransformType | None]
        | None = None,
        param: bool = False,
        default: DefaultType,
    ):
        # We use a value kwarg to pass parameters from the merger to attributes, so we need to make sure the transforms
        # can accept it. Should probably come up with a better way of handling this
        if transform is None:
            transform = cast(
                Callable[Concatenate[ScrapeType, ...], TransformType | None],
                _default_transform,
            )
        self._transform: Callable[
            Concatenate[ScrapeType, ...], TransformType | None
        ] = transform
        self.default: DefaultType = default
        self.param: bool = param
        self.name: str = ""

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
        try:
            f = owner.model._meta.get_field(self.name)
        except FieldDoesNotExist as e:
            owner.errors.append(e)
            return
        if isinstance(f, GenericForeignKey):
            owner.errors.append(
                TypeError(
                    f"{self.name}: Generic foreign keys are not supported yet."
                )
            )
            return
        owner.errors += self.validate(f)

    def transform(
        self, d: ScrapeType, value: TransformType | None = None
    ) -> TransformType | DefaultType:
        if self.param:
            v = self._transform(d, value=value)
        else:
            v = self._transform(d)

        if v is None:
            return self.default
        return v


class AttributeMerger[ScrapeType, TransformType](
    MergerSpecification[
        ScrapeType, TransformType, TransformType, TransformType | None
    ]
):
    """Class encapsulating logic for merging a single attribute from a scrape into a DB object.

    :param transform: Defines how to get the DB value from the scrape data
    :param strategy: How to behave when data is present in the scrape and DB. Defaults to overwriting the DB value
        only when the scraped value is present (not `None`), so a partial scrape won't overwrite existing data."""

    __slots__ = "strategy"

    def __init__(
        self,
        transform: Any
        | None = None,  # Generic callables confuse mypy; should be Callable[Concatenate[D, ...], T | None] | None
        strategy: Callable[
            Concatenate[TransformType | None, TransformType | None, ...],
            TransformType | None,
        ] = overwrite_if_present,
        param: bool = False,
        *,
        default: TransformType | None = None,
    ):
        super().__init__(transform=transform, param=param, default=default)
        self.strategy: Callable[
            Concatenate[TransformType | None, TransformType | None, ...],
            TransformType | None,
        ] = strategy


def Attribute[TransformType](
    transform: Any
    | None = None,  # Generic callables confuse mypy; should be Callable[Concatenate[D, ...], T | None] | None
    strategy: Callable[
        Concatenate[TransformType | None, TransformType | None, ...],
        TransformType | None,
    ] = overwrite_if_present,
    param: bool = False,
    *,
    default: TransformType | None = None,
) -> Any:
    return AttributeMerger(transform, strategy, param, default=default)


class RelatedMerger[
    ScrapeType,
    TransformType,
    MergeType,
    DefaultType,
    RM: Model,
](MergerSpecification[ScrapeType, TransformType, MergeType, DefaultType], ABC):
    __slots__ = "merger"

    def __init__(
        self,
        merger: "type[Merger[MergeType, RM]]",
        transform: Callable[Concatenate[ScrapeType, ...], TransformType | None]
        | None = None,
        param: bool = False,
        *,
        default: DefaultType,
    ):
        super().__init__(transform=transform, param=param, default=default)
        self.merger: type[Merger[MergeType, RM]] = merger

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
    def merge(self, parent: RM, scrape: ScrapeType) -> MergeResult[Any]: ...


class OneToOneMerger[ScrapeType, TransformType, RM: Model](
    RelatedMerger[
        ScrapeType,
        TransformType,
        TransformType,
        None,
        RM,
    ]
):
    """Class encapsulating logic for merging a one-to-one relationship."""

    def __init__(
        self,
        merger: "type[Merger[TransformType, RM]]",
        transform: Callable[Concatenate[ScrapeType, ...], TransformType | None]
        | None = None,
    ):
        super().__init__(merger=merger, transform=transform, default=None)

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.one_to_one:
            errors.append(TypeError(f"{self.name}: Is not a one-to-one field"))
        return errors

    def merge(self, parent: RM, scrape: ScrapeType) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship."""
        merger_input = self.transform(scrape)
        if merger_input is None:
            return MergeResult.unnecessary()

        db_obj = cast(RM | None, getattr(parent, self.name))
        result = self.merger.merge(merger_input, existing=db_obj)
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


def OneToOneRelation[ScrapeType, TransformType, RM: Model](
    merger: "type[Merger[TransformType, RM]]",
    transform: Callable[Concatenate[ScrapeType, ...], TransformType | None]
    | None = None,
) -> Any:
    return OneToOneMerger(merger, transform)


class NToManyMerger[ScrapeType, TransformType, RM: Model](
    RelatedMerger[
        ScrapeType,
        Sequence[TransformType],
        TransformType,
        Sequence[TransformType],
        RM,
    ],
    ABC,
):
    """Class encapsulating logic for merging an N-to-many relationship."""

    def __init__(
        self,
        merger: "type[Merger[TransformType, RM]]",
        transform: Callable[
            Concatenate[ScrapeType, ...], Sequence[TransformType]
        ]
        | None = None,
    ):
        super().__init__(merger=merger, transform=transform, default=[])


class OneToManyMerger[ScrapeType, TransformType, RM: Model, ParamType](
    NToManyMerger[ScrapeType, TransformType, RM]
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

    def merge(self, parent: RM, scrape: ScrapeType) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship."""
        merger_input = self.transform(scrape)
        if not merger_input:
            return MergeResult.unnecessary()

        # A lone `str`/`bytes` is iterable but is not a collection of
        # children -- iterating it would silently feed characters to the
        # child merger.
        if isinstance(merger_input, (str, bytes)):
            return MergeResult.failed(self.merger.model.__name__)
        result = MergeResult.unnecessary()
        related_manager: RelatedManager[Any] = getattr(parent, self.name)
        for child in cast(Iterable[Any], merger_input):
            result |= self.merger.merge(
                child, manager=related_manager, params=None
            )
        #     children.append(cast(Model, child_obj))
        # related_manager.add(*children)
        return result


def OneToManyRelation[ScrapeType, TransformType, RM: Model](
    merger: "type[Merger[TransformType, RM]]",
    transform: Callable[Concatenate[ScrapeType, ...], Sequence[TransformType]]
    | None = None,
) -> Any:
    return OneToManyMerger(merger, transform)


class MergerSpecRegistry[ScrapeType]:
    def __init__(
        self,
        *,
        related: dict[str, RelatedMerger[ScrapeType, Any, Any, Any, Model]]
        | None = None,
        attr: dict[str, AttributeMerger[ScrapeType, Any]] | None = None,
    ):
        self.related: dict[
            str, RelatedMerger[ScrapeType, Any, Any, Any, Model]
        ] = related or {}
        self.attr: dict[str, AttributeMerger[ScrapeType, Any]] = attr or {}

    def __copy__(self) -> Self:
        return self.__class__(related=self.related, attr=self.attr)

    def __or__(self, other: Self) -> Self:
        return self.__class__(
            related=self.related | other.related, attr=self.attr | other.attr
        )

    def update(self, other: Self):
        self.related.update(other.related)
        self.attr.update(other.attr)

    def register(self, spec: MergerSpecification[ScrapeType, Any, Any, Any]):
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
        cls, name: str, bases: tuple[type, ...], /, **kwargs
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
        registry: MergerSpecRegistry[Any] = MergerSpecRegistry()
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


class Merger[D, M: Model](metaclass=MergerMeta):
    """Base class for a merger which takes in `D` and merges it into `model`. Subclasses should generally not be
    instantiated; methods and attributes should be accessed directly from the class.

    :cvar model: The model this merger applies to.
    :cvar atomic: Whether to wrap the entire merge operation -- the object's own attributes *and* all related/child
        mergers -- in a single `transaction.atomic()` block, so the whole tree commits together or rolls back together
        if an exception is raised. Nested mergers that set their own `atomic` value simply create savepoints within
        this block.
    :cvar key: A natural key to use for looking up objects in the DB; used in the default `get_existing` implementation.
    :cvar errors: A list of errors encountered during validation of this merger. These will be surfaced after the merger
        is fully constructed and will prevent the `merge` method from being called."""

    model: ClassVar[type[Model]]
    atomic: ClassVar[bool] = False
    key: ClassVar[Iterable[str]] = []
    errors: ClassVar[list[Exception]]
    __registry__: ClassVar[MergerSpecRegistry[Any]]

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

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
    def validate(d: D) -> bool:
        """Validate the input data before attempting a merge operation

        :param d: Input data to the merge
        :return: True if the input is valid and the merge operation can proceed. False if the merge operation should be
            canceled."""
        return True

    @staticmethod
    def after(d: D, m: M | None, r: MergeResult[Any]) -> None:
        """Run extra processes after the merge operation completes or fails.

        :param d: Input data to the merge
        :param m: Merged object or None if the merge failed at this level
        :param r: Result of the merge operation"""
        ...

    @classmethod
    def get_existing(cls, d: D, manager: Manager[Model]) -> M | None:
        """Attempts to find an existing object in the DB to merge into based on the natural key

        Raises `MultipleObjectsReturned` if the natural key matches more than one
        object; callers are responsible for turning that into a merge failure.

        :param d: The scraped data to look up
        :param manager: The manager to use for lookups"""
        try:
            return cast(
                M,
                manager.get(
                    **{
                        name: cls.__registry__.attr[name].transform(d)
                        for name in cls.key
                    }
                ),
            )
        except cls.model.DoesNotExist:  # type: ignore[attr-defined]
            return None

    @classmethod
    def merge(
        cls,
        d: D,
        *,
        existing: M | None = None,
        manager: Manager[Model] | None = None,
        **kwargs: Any,
    ) -> MergeResult[Any]:
        """Merge scraped data into the DB.

        :param d: The input data to merge
        :param existing: An existing object to merge into, skipping lookup. Primarily useful for merging one-to-one
            relationships and should generally not be passed.
        :param manager: The manager to use for looking up the existing object. If not provided, the default manager for
            the model will be used. Primarily useful for related-object mergers."""
        if not cls.validate(d):
            logger.error(f"Merger {cls.__name__} received invalid input.")
            return MergeResult.failed(cls.model.__name__)

        if manager is None:
            manager = cls.model._default_manager

        if existing is None:
            try:
                existing = cls.get_existing(d, manager)
            except cls.model.MultipleObjectsReturned:  # type: ignore[attr-defined]
                logger.error(
                    "Merger %s found multiple objects; skipping merge.",
                    cls.__name__,
                )
                return MergeResult.failed(cls.model.__name__)

        if cls.atomic:
            with transaction.atomic():
                result, out_obj = cls._merge_tree(
                    d, existing, manager, **kwargs
                )
        else:
            result, out_obj = cls._merge_tree(d, existing, manager, **kwargs)
        cls.after(d, out_obj, result)
        return result

    @classmethod
    def _merge_tree(
        cls, d: D, db_obj: M | None, manager: Manager[Model], **kwargs: Any
    ) -> tuple[MergeResult[Any], M | None]:
        """Merge the object's own attributes and then all of its related/child
        mergers, returning the combined result.

        When `atomic` is set, the caller runs this inside a single
        `transaction.atomic()` block, so the object and its whole related tree
        commit or roll back together.

        :param d: The input data to merge
        :param db_obj: The object in the DB to merge into, if it exists

        :return: The result of the merge operation and the (possibly unsaved) object"""
        result = MergeResult.unnecessary()
        scrape_values = {
            name: am.transform(d, value=kwargs.get(name, None))
            for name, am in cls.__registry__.attr.items()
        }

        if db_obj is None:
            db_obj = cast(
                M,
                manager.create(**scrape_values),
            )
            result = MergeResult.created(cls.model.__name__, db_obj.pk)
        else:
            update = False
            for name, scrape_value in scrape_values.items():
                db_value = getattr(db_obj, name)
                merged_value = cls.__registry__.attr[name].strategy(
                    scrape_value,
                    db_value,
                )
                if merged_value != db_value:
                    setattr(db_obj, name, merged_value)
                    update = True

            if update:
                db_obj.save()
                result = MergeResult.updated(cls.model.__name__, db_obj.pk)

        for rm in cls.__registry__.related.values():
            result |= rm.merge(db_obj, d)

        return result, db_obj
