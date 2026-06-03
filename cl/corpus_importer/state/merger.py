import logging
import types
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterable, Mapping
from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
    ClassVar,
    get_args,
    get_origin,
    get_type_hints,
    override,
)

from django.db import transaction
from django.db.models import Model

from cl.corpus_importer.state.utils import MergeResult
from cl.lib.utils import is_iter

logger = logging.getLogger(__name__)


class InputMap[ScrapedData, Output]:
    """Apply a transformation to input data before passing it to a merger.

    :ivar map: Function to apply to input data. Should be a lambda in most cases.
    """

    def __init__(
        self, map: Callable[[ScrapedData], Output] | None = None
    ) -> None:
        self._map: Callable[[ScrapedData], Output | None] | None = map

    def map(self, i: ScrapedData) -> Output | None:
        if self._map is None:
            raise NotImplementedError(
                f"{type(self).__name__} was instantiated without a mapping function; pass one to __init__ or override map()."
            )
        return self._map(i)


class InputField[ScrapedData, Output](InputMap[ScrapedData, Output]):
    """Utility transformation to return a field from the input data unchanged.

    :ivar path: The path to the relevant field. Will handle dictionaries, objects, and combinations thereof."""

    def __init__(self, *path: str, default: Output | None = None) -> None:
        if not path:
            raise ValueError("Path must not be empty")
        super().__init__()
        self.path: list[str] = list(path)
        self.default: Output | None = default

    @override
    def map(self, i: ScrapedData) -> Output | None:
        current: Any = i
        for p in self.path:
            if isinstance(current, dict) and p in current:
                current = current[p]
            elif hasattr(current, p):
                current = getattr(current, p)
            else:
                logger.error(f"Could not find {self.path} in input")
                return self.default
        return current


class NeverMapping[ScrapedData, T](InputMap[ScrapedData, T]):
    """Transform that always returns None. Useful for testing or overriding base class mappings."""

    @override
    def map(self, i: ScrapedData) -> None:
        return None


class ParameterMapping[T](InputMap[T, T]):
    """Mapping indicating that a value should always be passed as a parameter to the merge method. Useful for passing
    information which won't change over the course of many merges (i.e., a parent `Docket` for `DocketEntry`s)."""

    @override
    def map(self, i: T) -> T:
        return i


Parameter = ParameterMapping[Any]()
"""Shorthand for an attribute which must be passed as a parameter to the merge method."""


class MergeStrategy[T](ABC):
    """Indicates the approach to take when data differs in the scrape and DB."""

    @abstractmethod
    def merge_values(self, scrape: T, db: T) -> T:
        """Computes what value should be written when data is present in the scrape and DB.

        :param scrape: The value from the scrape
        :param db: The value from the DB
        :return: The value to write. If this is equal to `db` nothing will be written."""
        raise NotImplementedError


class OverwriteExisting[T](MergeStrategy[T]):
    """Merge strategy that always overwrites the existing value with the scraped value."""

    @override
    def merge_values(self, scrape: T, db: T) -> T:
        return scrape


@dataclass
class OverwriteConditionally[T](MergeStrategy[T]):
    """Merge strategy that only overwrites the existing value if the condition is met.

    :param condition: Function that takes the scraped and DB values and returns True if the DB value should be
        overwritten."""

    condition: Callable[[T, T], bool]

    @override
    def merge_values(self, scrape: T, db: T) -> T:
        if self.condition(scrape, db):
            return scrape
        return db


class OverwriteIfPresent[T](MergeStrategy[T]):
    """Merge strategy that overwrites the existing value only when the scraped
    value is present (i.e. not `None`), otherwise keeping the DB value.

    This is the default strategy so that a partial scrape -- one that is missing
    a field it didn't manage to extract -- does not clobber good data already in
    the DB. Note that "present" means `not None`: a scraped empty string or `0`
    is treated as a real value and will overwrite the DB value. Use
    `OverwriteExisting` if `None` should be written, or `OverwriteConditionally`
    for finer-grained control."""

    @override
    def merge_values(self, scrape: T, db: T) -> T:
        return db if scrape is None else scrape


class AttributeMerger[ScrapedData, T]:
    """Class encapsulating logic for merging a single attribute from a scrape into a DB object.

    :param transform: Defines how to get the DB value from the scrape data using a subclass of `InputMap`
    :param strategy: How to behave when data is present in the scrape and DB. Defaults to overwriting the DB value
        only when the scraped value is present (not `None`), so a partial scrape won't clobber existing data."""

    def __init__(
        self,
        transform: InputMap[ScrapedData, T],
        *,
        strategy: MergeStrategy[T] = OverwriteIfPresent(),
    ) -> None:
        self.transform: InputMap[ScrapedData, T] = transform
        self.strategy: MergeStrategy[T] = strategy
        self.name: str = ""

    def __attach_to_merger__(
        self, merger: "type[Merger[Any, Any]]", attr_name: str
    ) -> None:
        """Run any special logic needed to attach this to a Merger object."""
        self.name = attr_name

    def get_value(
        self, i: ScrapedData, param_value: T | None = None
    ) -> T | None:
        """Compute the value of an attribute from scraped data.

        :param i: The full scrape data for the object being merged
        :param param_value: Value passed as a kwarg to the merge method. Only used if `transform` is `Parameter`."""
        if isinstance(self.transform, ParameterMapping):
            return param_value
        return self.transform.map(i)

    def merge_values(self, scrape: T, db: T) -> T:
        """Merge the values of two attributes (scrape and DB) and return the merged value.

        Shorthand for `self.strategy.merge_values(scrape, db)`.

        :param scrape: The value from the scrape
        :param db: The value from the DB"""
        return self.strategy.merge_values(scrape, db)


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


class RelatedMerger:
    """Class encapsulating logic for merging one or more related objects. Can be used to merge one-to-one relationships
    or parent-child relationships.

    :ivar merger: The `Merger` to use for the related object
    :ivar transform: Defines how to get the input value for `merger.merge` using a subclass of `InputMap`
    :ivar relationship: The type of relationship to merge"""

    def __init__(
        self,
        merger: "type[Merger[Any, Any]]",
        transform: InputMap[Any, Any],
        *,
        relationship: RelationshipType,
    ) -> None:
        self.merger: type[Merger[Any, Any]] = merger
        self.transform: InputMap[Any, Any] = transform
        self.relationship: RelationshipType = relationship
        self.name: str = ""

    def __attach_to_merger__(
        self, merger: "type[Merger[Any, Any]]", attr_name: str
    ) -> None:
        """Run any special logic needed to attach this to a Merger object. Should be run after all class setup code for
        the parent merger."""
        self.name = attr_name

    def _merge_one_to_one(
        self, parent: Model, merger_input: Any
    ) -> MergeResult[Any]:
        db_obj = getattr(parent, self.name)
        if db_obj is None:
            result = self.merger.merge(merger_input)
            model = self.merger.__model__
            model_name = model.__name__
            if model_name in result.creates:
                db_obj_pk = next(iter(result.creates[model_name]))
                setattr(parent, f"{self.name}_id", db_obj_pk)
                # The parent was already fully saved by `_merge_object`; only
                # the freshly-set FK needs to be written back.
                parent.save(update_fields=[f"{self.name}_id"])
            return result
        return self.merger.merge(merger_input, existing=db_obj)

    def _merge_child(
        self, parent: Model, merger_input: Any, parent_key: str
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
            return MergeResult.failed(self.merger.__model__.__name__)
        result = MergeResult.unnecessary()
        for child in merger_input:
            result |= self.merger.merge(child, **{parent_key: parent})
        return result

    def merge(self, parent: Model, i: Any) -> MergeResult[Any]:
        """Run the merge method on the appropriate inputs for the given relationship.

        For one-to-one relationships, the input is transformed then passed directly to the related merger. For
        parent-child relationships, we first check if the input is iterable and then run the related merger for each
        item, passing the parent object as a parameter.

        :param parent: The parent of the object being merged. Must already exist in the DB when this method is called.
        :param i: The input data for the object being merged."""
        merger_input = self.transform.map(i)

        match self.relationship:
            case OneToOneRelationship():
                return self._merge_one_to_one(parent, merger_input)
            case ChildRelationship(parent=parent_key):
                return self._merge_child(parent, merger_input, parent_key)


def get_ancestor_classes(cls: type) -> Generator[type]:
    """Get all ancestor classes of a class, including the class itself

    :param cls: The class to get ancestors for"""
    for base in types.get_original_bases(cls):
        if isinstance(base, type):
            yield from get_ancestor_classes(base)
        yield base


class Merger[ScrapedData, DBModel: Model](ABC):
    """Base class for a merger which takes in `ScrapedData` and merges it into `DBModel`. Subclasses should generally
    not be instantiated; methods and attributes should be accessed directly from the class.

    :ivar atomic: Whether to wrap the entire merge operation -- the object's own attributes *and* all related/child
        mergers -- in a single `transaction.atomic()` block, so the whole tree commits together or rolls back together
        if an exception is raised. Nested mergers that set their own `atomic` value simply create savepoints within
        this block.
    :ivar existing: A natural key or a function to find DB objects to merge into. Setting this to an iterable value
        and using natural key lookups is recommended, but if more complex logic is necessary, this can be a method
        that takes in a `DBModel` object and returns the matching object from the DB or `None` if none was found."""

    __attr_mergers__: dict[str, AttributeMerger[ScrapedData, Any]]
    __related_mergers__: ClassVar[dict[str, RelatedMerger]]
    __model__: type[DBModel]
    __default_attrs__: dict[str, Any]
    _uses_natural_key: ClassVar[bool] = True
    atomic: ClassVar[bool] = False
    # I'd like to make this a ClassVar for static type checking, but that's not allowed for some reason
    existing: Iterable[str] | Callable[[DBModel], DBModel | None] = []

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        annotated: list[
            tuple[
                str,
                list[AttributeMerger[Any, Any]],
                list[RelatedMerger],
            ]
        ] = [
            (
                name,
                [
                    a
                    for a in hint.__metadata__
                    if isinstance(a, AttributeMerger)
                ],
                [a for a in hint.__metadata__ if isinstance(a, RelatedMerger)],
            )
            for name, hint in get_type_hints(cls, include_extras=True).items()
            if not name.startswith("_") and get_origin(hint) is Annotated
        ]

        for name, attr_mergers, related_mergers in annotated:
            if len(attr_mergers) + len(related_mergers) > 1:
                raise TypeError(
                    f"Only one attribute merger or related merger is allowed per attribute: {name}"
                )

        cls.__attr_mergers__ = {
            name: attr_mergers[0]
            for name, attr_mergers, _ in annotated
            if attr_mergers
        }
        cls.__related_mergers__ = {
            name: related_mergers[0]
            for name, _, related_mergers in annotated
            if related_mergers
        }

        merger_bases = {
            base
            for base in get_ancestor_classes(cls)
            if get_origin(base) is Merger
        }
        if len(merger_bases) > 1:
            raise TypeError(
                f"Merger must only be a subclass of one Merger (got {merger_bases})"
            )
        if not merger_bases:
            raise TypeError(
                "Merger must be a subclass of Merger (I don't know how you managed to do this tbh)."
            )
        merger_base = merger_bases.pop()
        merger_type_args = get_args(merger_base)
        if len(merger_type_args) != 2:
            raise TypeError(
                f"Merger must be a subclass of Merger[ScrapedData, DBModel] (got {merger_type_args})"
            )
        _, db_model_type = merger_type_args
        if not issubclass(db_model_type, Model):
            raise TypeError(
                f"DBModel must be a subclass of Model (got {db_model_type})"
            )

        cls.__model__ = db_model_type

        cls.__default_attrs__ = {
            name: getattr(cls, name)
            for name in cls.__attr_mergers__
            if hasattr(cls, name)
        }

        for name, am in cls.__attr_mergers__.items():
            am.__attach_to_merger__(cls, name)
        for name, rm in cls.__related_mergers__.items():
            rm.__attach_to_merger__(cls, name)

    @staticmethod
    def validate(i: ScrapedData) -> bool:
        """Validate the input data before attempting a merge operation

        :param i: Input data to the merge
        :return: True if the input is valid and the merge operation can proceed. False if the merge operation should be
            canceled."""
        return True

    @staticmethod
    def after(i: ScrapedData, m: DBModel | None, r: MergeResult[Any]) -> None:
        """Run extra processes after the merge operation completes or fails.

        :param i: Input data to the merge
        :param m: Merged object or None if the merge failed at this level
        :param r: Result of the merge operation"""
        ...

    @classmethod
    def get_existing(cls, i: DBModel) -> DBModel | None:
        """Attempts to find an existing object in the DB to merge into based on either the natural key or a custom
        lookup function.

        Raises `MultipleObjectsReturned` if the natural key matches more than one
        object; callers are responsible for turning that into a merge failure.

        :param i: The object to attempt to find a match for"""
        if callable(cls.existing):
            return cls.existing(i)
        try:
            return cls.__model__._default_manager.get(
                **{k: getattr(i, k) for k in cls.existing}
            )
        except cls.__model__.DoesNotExist:
            return None

    @classmethod
    def merge(
        cls, i: ScrapedData, *, existing: DBModel | None = None, **kwargs: Any
    ) -> MergeResult[Any]:
        """Merge scraped data into the DB.

        :param i: The input data to merge
        :param existing: An existing object to merge into, skipping lookup. Primarily useful for merging one-to-one
            relationships and should generally not be passed."""
        if not cls.validate(i):
            logger.error(f"Merger {cls.__name__} received invalid input.")
            return MergeResult.failed(cls.__name__)

        defaults = cls.__default_attrs__ | kwargs
        obj = cls.__model__(
            **{
                name: am.get_value(i, defaults.get(name, None))
                for name, am in cls.__attr_mergers__.items()
            }
        )

        if cls.atomic:
            with transaction.atomic():
                result = cls._merge_tree(obj, i, existing=existing)
        else:
            result = cls._merge_tree(obj, i, existing=existing)
        cls.after(i, obj, result)
        return result

    @classmethod
    def _merge_tree(
        cls, obj: DBModel, i: ScrapedData, *, existing: DBModel | None
    ) -> MergeResult[Any]:
        """Merge the object's own attributes and then all of its related/child
        mergers, returning the combined result.

        When `atomic` is set the caller runs this inside a single
        `transaction.atomic()` block, so the object and its whole related tree
        commit or roll back together."""
        result, db_obj = cls._merge_object(obj, existing=existing)
        if not result.failures:
            for rm in cls.__related_mergers__.values():
                result |= rm.merge(db_obj, i)
        return result

    @classmethod
    def _merge_object(
        cls,
        scrape_obj: DBModel,
        *,
        existing: DBModel | None = None,
    ) -> tuple[MergeResult[Any], DBModel]:
        if existing is None:
            try:
                db_obj = cls.get_existing(scrape_obj)
            except cls.__model__.MultipleObjectsReturned:
                logger.error(
                    "Merger %s found multiple objects for natural key %s; skipping merge.",
                    cls.__name__,
                    cls.existing,
                )
                return MergeResult.failed(cls.__model__.__name__), scrape_obj
        else:
            db_obj = existing

        if db_obj is None:
            scrape_obj.save()
            return MergeResult.created(
                cls.__model__.__name__, scrape_obj.pk
            ), scrape_obj

        update = False
        for name, attr_merger in cls.__attr_mergers__.items():
            scrape_value = getattr(scrape_obj, name)
            db_value = getattr(db_obj, name)
            merged_value = attr_merger.merge_values(scrape_value, db_value)
            if merged_value != db_value:
                setattr(db_obj, name, merged_value)
                update = True

        if update:
            db_obj.save()
            return MergeResult.updated(
                cls.__model__.__name__, db_obj.pk
            ), db_obj
        return MergeResult.unnecessary(), db_obj
