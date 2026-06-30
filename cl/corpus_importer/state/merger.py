import logging
import typing
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


class MergerSpecification[
    ScrapeType,
    TransformType,
    DefaultType,
    MergeType,
    ParamType,
]:
    __slots__: tuple[str, ...] = "name", "transform", "default"

    def __init__(
        self,
        *,
        transform: Callable[
            [ScrapeType, ParamType], TransformType | DefaultType
        ]
        | None = None,
        default: DefaultType,
    ):
        self.transform: Callable[
            [ScrapeType, ParamType], TransformType | DefaultType
        ] = transform or self._default_transform
        self.default: DefaultType = default
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

    def _default_transform(
        self, scrape: ScrapeType, params: ParamType
    ) -> TransformType | DefaultType:
        if params is None:
            return self.default
        if isinstance(params, dict):
            return params.get(self.name, self.default)
        return getattr(params, self.name, self.default)


class AttributeMerger[ScrapeType, TransformType, ParamType](
    MergerSpecification[
        ScrapeType, TransformType, TransformType | None, ScrapeType, ParamType
    ],
    Any,
):
    """Class encapsulating logic for merging a single attribute from a scrape into a DB object.

    :param transform: Defines how to get the DB value from the scrape data
    :param strategy: How to behave when data is present in the scrape and DB. Defaults to overwriting the DB value
        only when the scraped value is present (not `None`), so a partial scrape won't overwrite existing data."""

    __slots__: tuple[str, ...] = ("strategy",)

    def __init__(
        self,
        transform: Any
        | None = None,  # Generic callables confuse mypy; should be Callable[Concatenate[D, ...], T | None] | None
        strategy: Callable[
            Concatenate[TransformType | None, TransformType | None, ...],
            TransformType | None,
        ] = overwrite_if_present,
        default: TransformType | None = None,
    ):
        super().__init__(transform=transform, default=default)
        self.strategy: Callable[
            Concatenate[TransformType | None, TransformType | None, ...],
            TransformType | None,
        ] = strategy


class SubMerger[
    ScrapeType,
    TransformType,
    DefaultType,
    RM: Model,
    MergeType,
    ParamType,
](
    MergerSpecification[
        ScrapeType, TransformType, DefaultType, MergeType, ParamType
    ]
):
    __slots__: tuple[str, ...] = ("merger",)

    def __init__(
        self,
        *,
        merger: "type[Merger[MergeType, RM, Any]]",
        transform: Callable[Concatenate[ScrapeType, ...], TransformType]
        | None = None,
        default: DefaultType,
    ):
        super().__init__(transform=transform, default=default)
        self.merger: type[Merger[MergeType, RM, Any]] = merger

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

    def merge(
        self, parent: RM, i: ScrapeType, params: ParamType
    ) -> MergeResult[Any]:
        raise NotImplementedError


class OneToOneMerger[ScrapeType, TransformType, RM: Model, ParamType](
    SubMerger[
        ScrapeType,
        TransformType | None,
        TransformType | None,
        RM,
        TransformType,
        ParamType,
    ],
    Any,
):
    """Class encapsulating logic for merging a one-to-one relationship."""

    def __init__(
        self,
        merger: "type[Merger[TransformType, RM, ParamType]]",
        transform: Callable[Concatenate[ScrapeType, ...], TransformType | None]
        | None = None,
        default: TransformType | None = None,
    ):
        super().__init__(merger=merger, transform=transform, default=default)

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.one_to_one:
            errors.append(TypeError(f"{self.name}: Is not a one-to-one field"))
        return errors

    def merge(
        self, parent: RM, i: ScrapeType, params: ParamType
    ) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship."""
        merger_input = self.transform(i, params)
        if merger_input is None:
            return MergeResult.unnecessary()

        db_obj = cast(RM | None, getattr(parent, self.name))
        result = self.merger(
            merger_input, existing=db_obj, params=None
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


class NToManyMerger[ScrapeType, TransformType, RM: Model, ParamType](
    SubMerger[
        ScrapeType,
        Sequence[TransformType],
        Sequence[TransformType],
        RM,
        TransformType,
        ParamType,
    ]
):
    """Class encapsulating logic for merging an N-to-many relationship."""

    def __init__(
        self,
        merger: "type[Merger[TransformType, RM, ParamType]]",
        transform: Callable[
            Concatenate[ScrapeType, ...], Sequence[TransformType]
        ]
        | None = None,
        default: Sequence[TransformType] | None = None,
    ):
        if default is None:
            default = []
        super().__init__(merger=merger, transform=transform, default=default)


class OneToManyMerger[ScrapeType, TransformType, RM: Model, ParamType](
    NToManyMerger[ScrapeType, TransformType, RM, ParamType], Any
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

    def merge(
        self, parent: RM, i: ScrapeType, params: ParamType
    ) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship."""
        merger_input = self.transform(i, params)
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
            result |= self.merger(
                child, manager=related_manager, params=None
            ).merge()
        #     children.append(cast(Model, child_obj))
        # related_manager.add(*children)
        return result


class ManyToManyMerger[
    ScrapeType,
    TransformType,
    ThruM: Model,
    RM: Model,
    ParamType,
](NToManyMerger[ScrapeType, TransformType, RM, ParamType], Any):
    """Class encapsulating logic for merging a many-to-many relationship."""

    __slots__: tuple[str, ...] = ("through",)

    def __init__(
        self,
        merger: "type[Merger[TransformType, RM, ParamType]]",
        through: "type[Merger[TransformType, ThruM, ParamType]]",
        transform: Callable[
            Concatenate[ScrapeType, ...], Sequence[TransformType]
        ]
        | None = None,
        default: Sequence[TransformType] | None = None,
    ):
        super().__init__(merger, transform, default)
        self.through: type[Merger[TransformType, ThruM, ParamType]] = through

    def validate(self, field: Field | ForeignObjectRel) -> list[Exception]:
        errors = super().validate(field)
        if not field.many_to_many:
            errors.append(
                TypeError(f"{self.name}: Is not a many-to-many field")
            )
        return errors

    def merge(
        self, parent: RM, i: ScrapeType, params: ParamType
    ) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship."""
        merger_input = self.transform(i, params)
        if not merger_input:
            return MergeResult.unnecessary()

        raise NotImplementedError


class MergerSpecRegistry[ScrapeType, ParamType]:
    def __init__(
        self,
        *,
        related: dict[
            str, SubMerger[ScrapeType, Any, Any, Model, Any, ParamType]
        ]
        | None = None,
        attr: dict[str, AttributeMerger[ScrapeType, Any, ParamType]]
        | None = None,
    ):
        self.related: dict[
            str, SubMerger[ScrapeType, Any, Any, Model, Any, ParamType]
        ] = related or {}
        self.attr: dict[str, AttributeMerger[ScrapeType, Any, ParamType]] = (
            attr or {}
        )

    def __copy__(self) -> Self:
        return self.__class__(related=self.related, attr=self.attr)

    def __or__(self, other: Self) -> Self:
        return self.__class__(
            related=self.related | other.related, attr=self.attr | other.attr
        )

    def update(self, other: Self):
        self.related.update(other.related)
        self.attr.update(other.attr)

    def register(
        self, spec: MergerSpecification[ScrapeType, Any, Any, Any, ParamType]
    ):
        match spec:
            case AttributeMerger():
                self.attr[spec.name] = spec
            case SubMerger():
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


class Merger[ScrapeType, M: Model, ParamType](metaclass=MergerMeta):
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
    def validate(scrape: ScrapeType) -> bool:
        """Validate the input data before attempting a merge operation

        :param scrape: Input data to the merge
        :return: True if the input is valid and the merge operation can proceed. False if the merge operation should be
            canceled."""
        return True

    def __init__(
        self,
        d: ScrapeType,
        *,
        params: ParamType,
        existing: M | None = None,
        manager: Manager[M] | None = None,
    ):
        """Create an object to track the merge operation on the specified data.

        :param d: The scraped data to transform. Parameter values are passed as kwargs.
        :param existing: Optional existing object to override the lookup in `get_existing`.
        :param manager: The manager to use for lookups and creation of objects. Defaults to the model's default manager."""
        self.guarantee_valid()
        result = None
        valid = self.validate(d)
        if not valid:
            logger.error(
                f"Merger {self.__class__.__name__} received invalid input."
            )
            result = MergeResult.failed(self.model.__name__)

        self.scrape: ScrapeType = d
        self.params: ParamType = params
        self.result: MergeResult[Any] | None = result
        self.out: M | None = None

        self.transformed: dict[str, Any] = (
            {
                name: spec.transform(d, params)
                for name, spec in self.__registry__.attr.items()
            }
            | {
                name: spec.transform(d, params)
                for name, spec in self.__registry__.related.items()
            }
            if valid
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
            **{name: self.transformed[name] for name in self.key}
        )

    def merge(self) -> MergeResult[Any]:
        """Merge scraped data into the DB."""
        if self.result is not None:
            raise RuntimeError(
                f"Merger {self.__class__.__name__} already merged; cannot merge again."
            )
        if self.existing is None:
            try:
                self.existing = self.query().get()
            except self.model.MultipleObjectsReturned:  # type: ignore[attr-defined]
                logger.error(
                    "Merger %s found multiple objects; skipping merge.",
                    self.__class__.__name__,
                )
                self.result = MergeResult.failed(self.model.__name__)
                return self.result
            except self.model.DoesNotExist:  # type: ignore[attr-defined]
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
                }
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
                **{
                    name: self.transformed[name]
                    for name in self.__registry__.attr.keys()
                }
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
