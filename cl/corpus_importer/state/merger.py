import logging
import typing
from abc import ABC
from collections.abc import Callable, Iterable, Mapping
from typing import (
    Any,
    ClassVar,
    Concatenate,
    cast,
    override,
)

from django.db import transaction
from django.db.models import ForeignKey, ManyToManyField, Model, OneToOneField
from django.db.models.manager import Manager

from cl.corpus_importer.state.utils import MergeResult
from cl.lib.utils import is_iter

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


class MergerSpecification[D, T]:
    __slots__ = "name", "_transform", "default", "param"

    def __init__(
        self,
        transform: Callable[Concatenate[D, ...], T | None] | None = None,
        param: bool = False,
        default: T | None = None,
    ):
        # We use a value kwarg to pass parameters from the merger to attributes, so we need to make sure the transforms
        # can accept it. Should probably come up with a better way of handling this
        if transform is None:
            transform = cast(
                Callable[Concatenate[D, ...], T | None], _default_transform
            )
        self._transform: Callable[Concatenate[D, ...], T | None] = transform
        self.default: T | None = default
        self.param: bool = param
        self.name: str = ""

    def __set_name__(self, owner: type, name: str):
        self.name = name

    def transform(self, d: D, value: T | None = None) -> T | None:
        if self.param:
            v = self._transform(d, value=value)
        else:
            v = self._transform(d)

        if v is None:
            return self.default
        return v


class AttributeMerger[D, T](MergerSpecification[D, T]):
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
            Concatenate[T | None, T | None, ...], T | None
        ] = overwrite_if_present,
        param: bool = False,
        default: T | None = None,
    ):
        super().__init__(transform, param, default)
        self.strategy: Callable[
            Concatenate[T | None, T | None, ...], T | None
        ] = strategy


def Attribute[T](
    transform: Any
    | None = None,  # Generic callables confuse mypy; should be Callable[Concatenate[D, ...], T | None] | None
    strategy: Callable[
        Concatenate[T | None, T | None, ...], T | None
    ] = overwrite_if_present,
    param: bool = False,
    default: T | None = None,
) -> Any:
    return AttributeMerger(transform, strategy, param, default)


class SubMerger[D, T, RM: Model](MergerSpecification[D, T]):
    __slots__ = "merger"

    def __init__(
        self,
        merger: "type[Merger[T, RM]]",
        transform: Callable[Concatenate[D, ...], T | None] | None = None,
        param: bool = False,
        default: T | None = None,
    ):
        super().__init__(transform, param, default)
        self.merger: type[Merger[T, RM]] = merger

    def merge(self, parent: RM, i: D) -> MergeResult[Any]:
        raise NotImplementedError


class RelatedMerger[D, T, RM: Model](SubMerger[D, T, RM]):
    """Class encapsulating logic for merging one or more related objects. Can be used to merge one-to-one relationships
    or parent-child relationships.

    :ivar merger: The `Merger` to use for the related object"""

    def __init__(
        self,
        merger: "type[Merger[T, RM]]",
        transform: Any
        | None = None,  # Generic callables confuse mypy; should be Callable[Concatenate[D, ...], T | None] | None
        param: bool = False,
        default: T | None = None,
    ):
        super().__init__(merger, transform, param, default)
        self.merger: type[Merger[T, RM]] = merger

    def _merge_one_to_one(
        self, parent: Model, merger_input: T
    ) -> MergeResult[Any]:
        db_obj = getattr(parent, self.name)
        if db_obj is None:
            result = self.merger.merge(merger_input)
            model = self.merger.model
            model_name = model.__name__
            if model_name in result.creates:
                db_obj_pk = next(iter(result.creates[model_name]))
                setattr(parent, f"{self.name}_id", db_obj_pk)
                # The parent was already fully saved by `_merge_object`; only
                # the freshly-set FK needs to be written back.
                parent.save(update_fields=[f"{self.name}_id"])
            return result
        return self.merger.merge(merger_input, existing=db_obj)

    def _merge_related(
        self, parent: Model, merger_input: T
    ) -> MergeResult[Any]:
        # A lone `str`/`bytes`/`Mapping` is iterable but is not a collection of
        # children -- iterating it would silently feed characters or keys to the
        # child merger. Reject those (and anything not iterable at all).
        if isinstance(merger_input, (str, bytes, Mapping)) or not is_iter(
            merger_input
        ):
            return MergeResult.failed(self.merger.model.__name__)
        result = MergeResult.unnecessary()
        related_manager: RelatedManager[Any] = getattr(parent, self.name)
        for child in cast(Iterable[Any], merger_input):
            result |= self.merger.merge(child, manager=related_manager)
        return result

    @override
    def merge(self, parent: RM, i: D) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship.

        For one-to-one relationships, the input is transformed then passed directly to the related merger; a `None`
        transform result means there is no relative to merge and is skipped. For parent-child relationships, we first
        check if the input is iterable and then run the related merger for each item, passing the parent object as a
        parameter.

        :param parent: The parent of the object being merged. Must already exist in the DB when this method is called.
        :param i: The input data for the object being merged."""
        merger_input = self.transform(i, None)
        if merger_input is None:
            return MergeResult.unnecessary()

        f = parent._meta.get_field(self.name)

        # These should be initialization-time checks on subclasses of SubMerger, but for now this will do.
        # Party merger PR will handle the subclasses
        if f.one_to_one:
            return self._merge_one_to_one(parent, merger_input)
        elif f.one_to_many:
            return self._merge_related(parent, merger_input)
        elif f.many_to_many:
            raise NotImplementedError
        raise TypeError(f"Field {self.name} is not a related field.")


def Related[T, RM: Model](
    merger: "type[Merger[T, RM]]",
    transform: Any
    | None = None,  # Generic callables confuse mypy; should be Callable[Concatenate[D, ...], T | None] | None
    param: bool = False,
    default: T | None = None,
) -> Any:
    return RelatedMerger(merger, transform, param, default)


class Merger[D, M: Model](ABC):
    """Base class for a merger which takes in `D` and merges it into `model`. Subclasses should generally not be
    instantiated; methods and attributes should be accessed directly from the class.

    :ivar atomic: Whether to wrap the entire merge operation -- the object's own attributes *and* all related/child
        mergers -- in a single `transaction.atomic()` block, so the whole tree commits together or rolls back together
        if an exception is raised. Nested mergers that set their own `atomic` value simply create savepoints within
        this block.
    :ivar key: A natural key to use for looking up objects in the DB; used in the default `get_existing` implementation."""

    model: ClassVar[type[Model]]
    atomic: ClassVar[bool] = False
    key: ClassVar[Iterable[str]] = []
    __attr_mergers__: ClassVar[dict[str, AttributeMerger[Any, Any]]] = {}
    __related_mergers__: ClassVar[
        dict[str, RelatedMerger[Any, Any, Model]]
    ] = {}

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        errors: list[str] = []

        own_attrs = vars(cls).values()

        cls.__attr_mergers__ = cls.__attr_mergers__ | {
            value.name: cast(AttributeMerger[D, Any], value)
            for value in own_attrs
            if isinstance(value, AttributeMerger)
        }
        cls.__related_mergers__ = cls.__related_mergers__ | {
            value.name: cast(RelatedMerger[D, Any, Model], value)
            for value in own_attrs
            if isinstance(value, RelatedMerger)
        }

        model_fields = cls.model._meta.get_fields()
        fields = {field.name: field for field in model_fields}
        derived_fields: set[str] = {
            f.attname
            for f in model_fields
            if isinstance(f, ForeignKey | ManyToManyField | OneToOneField)
        }

        for name, _ in cls.__attr_mergers__.items():
            if name not in fields and name not in derived_fields:
                errors.append(
                    f"Attribute {name} not found on {cls.model.__name__}"
                )

        for name, rm in cls.__related_mergers__.items():
            if name not in fields:
                errors.append(
                    f"Related field {name} not found on {cls.model.__name__}"
                )
            if not fields[name].related_model:
                errors.append(
                    f"Field {name} on {cls.model.__name__} is not a related field"
                )
            if fields[name].related_model != rm.merger.model:
                errors.append(
                    f"Field {name} on {cls.model.__name__} is related to {rm.merger.model.__name__}, not {rm.merger.model.__name__}"
                )
            attname = getattr(fields[name], "attname", None)
            if attname is not None and attname in cls.__attr_mergers__:
                errors.append(
                    f"Cannot merge both {name} and {attname} on {cls.model.__name__}"
                )

        if errors:
            raise TypeError(
                "Invalid merger configuration:\n{}".format(
                    "\n".join(f"- {e}" for e in errors)
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
                        name: cls.__attr_mergers__[name].transform(d)
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
            for name, am in cls.__attr_mergers__.items()
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
                merged_value = cls.__attr_mergers__[name].strategy(
                    scrape_value,
                    db_value,
                )
                if merged_value != db_value:
                    setattr(db_obj, name, merged_value)
                    update = True

            if update:
                db_obj.save()
                result = MergeResult.updated(cls.model.__name__, db_obj.pk)

        for rm in cls.__related_mergers__.values():
            result |= rm.merge(db_obj, d)

        return result, db_obj
