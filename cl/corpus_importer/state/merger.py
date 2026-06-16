import inspect
import logging
from abc import ABC
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import (
    Any,
    ClassVar,
    Concatenate,
    cast,
)

from django.db import transaction
from django.db.models import Model

from cl.corpus_importer.state.utils import MergeResult
from cl.lib.utils import is_iter

logger = logging.getLogger(__name__)


def parameter[D, T](
    default: T | None = None,
) -> Callable[Concatenate[D, ...], T | None]:
    """Gets value from merger parameters

    Probably needs to be replaced eventually.

    :param default: Default value to use if the parameter is not present"""

    def f(d: D, value: T | None = default) -> T | None:
        if value is None:
            value = default
        return value

    return f


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


def _wrap_value_kwarg[T, **P](f: Callable[P, T]) -> Callable[P, T]:
    def g(*args: Any, value: T, **kwargs: Any) -> T:
        return f(*args, **kwargs)

    return g


@dataclass(slots=True)
class AttributeMerger[D, T](Any):
    """Class encapsulating logic for merging a single attribute from a scrape into a DB object.

    :param transform: Defines how to get the DB value from the scrape data
    :param strategy: How to behave when data is present in the scrape and DB. Defaults to overwriting the DB value
        only when the scraped value is present (not `None`), so a partial scrape won't overwrite existing data."""

    transform: Callable[Concatenate[D, ...], T]
    strategy: Callable[Concatenate[T | None, T | None, ...], T | None] = field(
        kw_only=True, default=overwrite_if_present
    )

    def __post_init__(self):
        # We use a value kwarg to pass parameters from the merger to attributes, so we need to make sure the transforms
        # can accept it. Should probably come up with a better way of handling this
        sig = inspect.signature(self.transform)
        if "value" not in sig.parameters and "kwargs" not in sig.parameters:
            self.transform = _wrap_value_kwarg(self.transform)


class OneToOneRelationship: ...


@dataclass
class ChildRelationship:
    parent: str


# Pretend Python has sum types
class Relationship:
    OneToOne: OneToOneRelationship = OneToOneRelationship()
    """One-to-one relationship. Parent objects have a foreign key to relatives."""
    Child: type[ChildRelationship] = ChildRelationship
    """Parent-child relationship. Child objects have a foreign key to the parent."""


RelationshipType = OneToOneRelationship | ChildRelationship


@dataclass(frozen=True, slots=True)
class RelatedMerger[ScrapedData, RelatedModel: Model, RelatedInput = Any](Any):
    """Class encapsulating logic for merging one or more related objects. Can be used to merge one-to-one relationships
    or parent-child relationships.

    :ivar merger: The `Merger` to use for the related object
    :ivar transform: Defines how to get the input value for `merger.merge` using a subclass of `InputMap`
    :ivar relationship: The type of relationship to merge"""

    merger: "type[Merger[RelatedInput, RelatedModel]]"
    transform: Callable[[ScrapedData], RelatedInput] = lambda x: cast(
        RelatedInput, x
    )
    relationship: RelationshipType = field(kw_only=True)
    gate: Callable[[ScrapedData], bool] = field(
        kw_only=True, default=lambda _: True
    )

    def _merge_one_to_one(
        self, parent: Model, merger_input: RelatedInput, *, name: str
    ) -> MergeResult[Any]:
        if merger_input is None:
            return MergeResult.unnecessary()
        db_obj = getattr(parent, name)
        if db_obj is None:
            result = self.merger.merge(merger_input)
            model = self.merger.model
            model_name = model.__name__
            if model_name in result.creates:
                db_obj_pk = next(iter(result.creates[model_name]))
                setattr(parent, f"{name}_id", db_obj_pk)
                # The parent was already fully saved by `_merge_object`; only
                # the freshly-set FK needs to be written back.
                parent.save(update_fields=[f"{name}_id"])
            return result
        return self.merger.merge(merger_input, existing=db_obj)

    def _merge_child(
        self, parent: Model, merger_input: RelatedInput, parent_key: str
    ) -> MergeResult[Any]:
        # An absent optional collection is not an error; there is simply nothing
        # to merge.
        if merger_input is None:
            return MergeResult.unnecessary()
        # A lone `str`/`bytes`/`Mapping` is iterable but is not a collection of
        # children -- iterating it would silently feed characters or keys to the
        # child merger. Reject those (and anything not iterable at all).
        if isinstance(merger_input, (str, bytes, Mapping)) or not is_iter(
            merger_input
        ):
            return MergeResult.failed(self.merger.model.__name__)
        result = MergeResult.unnecessary()
        parent_kwargs: dict[str, Any] = {parent_key: parent}
        for child in cast(Iterable[Any], merger_input):
            result |= self.merger.merge(child, **parent_kwargs)
        return result

    def merge(
        self, parent: Model, i: ScrapedData, *, name: str
    ) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship.

        For one-to-one relationships, the input is transformed then passed directly to the related merger; a `None`
        transform result means there is no relative to merge and is skipped. For parent-child relationships, we first
        check if the input is iterable and then run the related merger for each item, passing the parent object as a
        parameter.

        :param parent: The parent of the object being merged. Must already exist in the DB when this method is called.
        :param i: The input data for the object being merged.
        :param name: The name of the attribute on the parent object."""
        if not self.gate(i):
            return MergeResult.unnecessary()
        merger_input = self.transform(i)
        if merger_input is None:
            return MergeResult.unnecessary()

        match self.relationship:
            case OneToOneRelationship():
                return self._merge_one_to_one(parent, merger_input, name=name)
            case ChildRelationship(parent=parent_key):
                return self._merge_child(parent, merger_input, parent_key)


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

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        if not hasattr(cls, "__attr_mergers__"):
            cls.__attr_mergers__ = {}
        if not hasattr(cls, "__related_mergers__"):
            cls.__related_mergers__ = {}

        cls_attrs = [
            (name, getattr(cls, name))
            for name in dir(cls)
            if not name.startswith("_")
        ]

        cls.__attr_mergers__: dict[str, AttributeMerger[D, Any]] = (
            cls.__attr_mergers__
            | {
                name: cast(AttributeMerger[D, Any], value)
                for name, value in cls_attrs
                if isinstance(value, AttributeMerger)
            }
        )
        cls.__related_mergers__: dict[str, RelatedMerger[D, M]] = (
            cls.__related_mergers__
            | {
                name: cast(RelatedMerger[D, M], value)
                for name, value in cls_attrs
                if isinstance(value, RelatedMerger)
            }
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
    def get_existing(cls, d: M) -> M | None:
        """Attempts to find an existing object in the DB to merge into based on either the natural key or a custom
        lookup function.

        Raises `MultipleObjectsReturned` if the natural key matches more than one
        object; callers are responsible for turning that into a merge failure.

        :param d: The object to attempt to find a match for"""
        try:
            return cast(
                M,
                cls.model._default_manager.get(
                    **{k: getattr(d, k) for k in cls.key}
                ),
            )
        except cls.model.DoesNotExist:
            return None

    @classmethod
    def merge(
        cls, d: D, *, existing: M | None = None, **kwargs: Any
    ) -> MergeResult[Any]:
        """Merge scraped data into the DB.

        :param d: The input data to merge
        :param existing: An existing object to merge into, skipping lookup. Primarily useful for merging one-to-one
            relationships and should generally not be passed."""
        if not cls.validate(d):
            logger.error(f"Merger {cls.__name__} received invalid input.")
            return MergeResult.failed(cls.model.__name__)

        obj = cast(
            M,
            cls.model(
                **{
                    name: am.transform(d, value=kwargs.get(name, None))
                    for name, am in cls.__attr_mergers__.items()
                }
            ),
        )

        if cls.atomic:
            with transaction.atomic():
                result = cls._merge_tree(obj, d, existing=existing)
        else:
            result = cls._merge_tree(obj, d, existing=existing)
        cls.after(d, obj, result)
        return result

    @classmethod
    def _merge_tree(
        cls, obj: M, d: D, *, existing: M | None
    ) -> MergeResult[Any]:
        """Merge the object's own attributes and then all of its related/child
        mergers, returning the combined result.

        When `atomic` is set the caller runs this inside a single
        `transaction.atomic()` block, so the object and its whole related tree
        commit or roll back together."""
        result, db_obj = cls._merge_object(obj, existing=existing)
        if not result.failures:
            for name, rm in cls.__related_mergers__.items():
                result |= rm.merge(db_obj, d, name=name)
        return result

    @classmethod
    def _merge_object(
        cls,
        scrape_obj: M,
        *,
        existing: M | None = None,
    ) -> tuple[MergeResult[Any], M]:
        if existing is None:
            try:
                db_obj = cls.get_existing(scrape_obj)
            except cls.model.MultipleObjectsReturned:
                logger.error(
                    "Merger %s found multiple objects for natural key %s; skipping merge.",
                    cls.__name__,
                    cls.existing,
                )
                return MergeResult.failed(cls.model.__name__), scrape_obj
        else:
            db_obj = existing

        if db_obj is None:
            scrape_obj.save()
            return MergeResult.created(
                cls.model.__name__, scrape_obj.pk
            ), scrape_obj

        update = False
        for name, attr_merger in cls.__attr_mergers__.items():
            scrape_value = getattr(scrape_obj, name)
            db_value = getattr(db_obj, name)
            merged_value = attr_merger.strategy(scrape_value, db_value)
            if merged_value != db_value:
                setattr(db_obj, name, merged_value)
                update = True

        if update:
            db_obj.save()
            return MergeResult.updated(cls.model.__name__, db_obj.pk), db_obj
        return MergeResult.unnecessary(), db_obj
