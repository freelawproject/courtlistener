import logging
import types
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
    ClassVar,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    override,
)

from django.db import transaction
from django.db.models import Model
from openai._utils import is_iterable

from cl.corpus_importer.state.utils import MergeResult

logger = logging.getLogger(__name__)


class InputMap[ScrapedData, Output]:
    def __init__(
        self, map: Callable[[ScrapedData], Output] | None = None
    ) -> None:
        if map is not None:
            self._map: Callable[[ScrapedData], Output | None] = map

    def map(self, i: ScrapedData) -> Output | None:
        return self._map(i)


class InputField[ScrapedData, Output](InputMap[ScrapedData, Output]):
    def __init__(self, *path: str, default: Output | None = None) -> None:
        if not path:
            raise ValueError("Path must not be empty")
        super().__init__()
        self.path: list[str] = list(path)
        self.default: Output | None = default

    @override
    def map(self, i: ScrapedData) -> Output | None:
        current = i
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
    @override
    def map(self, i: ScrapedData) -> None:
        return None


class ParameterMapping[T](InputMap[T, T]):
    @override
    def map(self, i: T) -> T:
        return i


Parameter = ParameterMapping[Any]()


class MergeStrategy[T](ABC):
    @abstractmethod
    def merge_values(self, scrape: T, db: T) -> T:
        raise NotImplementedError


class OverwriteExisting[T](MergeStrategy[T]):
    @override
    def merge_values(self, scrape: T, db: T) -> T:
        return scrape


@dataclass
class OverwriteConditionally[T](MergeStrategy[T]):
    condition: Callable[[T, T], bool]

    @override
    def merge_values(self, scrape: T, db: T) -> T:
        if self.condition(scrape, db):
            return scrape
        return db


class AttributeMerger[ScrapedData, T]:
    def __init__(
        self,
        transform: InputMap[ScrapedData, T],
        *,
        strategy: MergeStrategy[T] = OverwriteExisting(),
    ) -> None:
        self.transform = transform
        self.strategy: MergeStrategy[T] = strategy
        self.name: str = ""

    def __attach_to_merger__(
        self, merger: "type[Merger[Any, Any]]", attr_name: str
    ) -> None:
        """Run any special logic needed to attach this to a Merger object. Should be run after all class setup code for
        the parent merger. For one-to-one relationships, register the name of the attribute this is attached to on the
        parent."""
        self.name = attr_name

    def get_value(
        self, i: ScrapedData, param_value: T | None = None
    ) -> T | None:
        """Compute the value of an attribute from scraped data."""
        if isinstance(self.transform, ParameterMapping):
            return param_value
        return self.transform.map(i)

    def merge_values(self, scrape: T, db: T) -> T:
        """Merge the values of two attributes (scrape and DB) and return the merged value."""
        return self.strategy.merge_values(scrape, db)


class OneToOneRelationship: ...


@dataclass
class ChildRelationship:
    parent: str


# Pretend Python has sum types
class Relationship:
    OneToOne: OneToOneRelationship = OneToOneRelationship()
    Child: type[ChildRelationship] = ChildRelationship


RelationshipType = OneToOneRelationship | ChildRelationship


class RelatedMerger:
    def __init__(
        self,
        merger: "type[Merger[Any, Any]]",
        transform: InputMap[Any, Any],
        *,
        relationship: RelationshipType,
    ) -> None:
        """

        :param merger:
        :param transform:
        :param relationship:
        """
        self.merger: type[Merger[Any, Any]] = merger
        self.transform: InputMap[Any, Any] = transform
        self.relationship: RelationshipType = relationship
        self.name: str = ""

    def __attach_to_merger__(
        self, merger: "type[Merger[Any, Any]]", attr_name: str
    ) -> None:
        """Run any special logic needed to attach this to a Merger object. Should be run after all class setup code for
        the parent merger. For one-to-one relationships, register the name of the attribute this is attached to on the
        parent."""
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
                parent.save()
            return result
        return self.merger.merge(merger_input, existing=db_obj)

    def _merge_child(
        self, parent: Model, merger_input: Any, parent_key: str
    ) -> MergeResult[Any]:
        if not is_iterable(merger_input):
            return MergeResult.failed(self.merger.__model__.__name__)
        result = MergeResult.unnecessary()
        for child in merger_input:
            result |= self.merger.merge(child, **{parent_key: parent})
        return result

    def merge(self, parent: Model, i: Any) -> MergeResult[Any]:
        merger_input = self.transform.map(i)

        match self.relationship:
            case Relationship.OneToOne:
                return self._merge_one_to_one(parent, merger_input)
            case Relationship.Child(parent_key):
                return self._merge_child(parent, merger_input, parent_key)
            case _:
                raise TypeError(
                    f"Invalid relationship type: {self.relationship}"
                )


def get_ancestor_classes(cls: type) -> Generator[type]:
    """Get all ancestor classes of a class, including the class itself"""
    for base in types.get_original_bases(cls):
        if isinstance(base, type):
            yield from get_ancestor_classes(base)
        yield base


class Merger[ScrapedData, DBModel: Model](ABC):
    __attr_mergers__: dict[str, AttributeMerger[ScrapedData, Any]]
    __related_mergers__: ClassVar[dict[str, RelatedMerger]]
    __model__: type[Model]
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
        if callable(cls.existing):
            return cls.existing(i)
        try:
            return cast(
                DBModel,
                cls.__model__.objects.get(
                    **{k: getattr(i, k) for k in cls.existing}
                ),
            )
        except cls.__model__.DoesNotExist:
            return None
        except cls.__model__.MultipleObjectsReturned:
            raise ValueError(
                f"Merger {cls.__name__} found multiple objects found for natural key {cls.existing}."
            )

    @classmethod
    def merge(
        cls, i: ScrapedData, *, existing: DBModel | None = None, **kwargs: Any
    ) -> MergeResult[Any]:
        if not cls.validate(i):
            logger.error(f"Merger {cls.__name__} received invalid input.")
            return MergeResult.failed(cls.__name__)

        defaults = cls.__default_attrs__ | kwargs
        obj = cast(
            DBModel,
            cls.__model__(
                **{
                    name: am.get_value(i, defaults.get(name, None))
                    for name, am in cls.__attr_mergers__.items()
                }
            ),
        )

        if cls.atomic:
            with transaction.atomic():
                result, db_obj = cls._merge_object(obj, existing=existing)
        else:
            result, db_obj = cls._merge_object(obj, existing=existing)

        if not result.failures:
            for _, rm in cls.__related_mergers__.items():
                result |= rm.merge(db_obj, i)
        cls.after(i, obj, result)
        return result

    @classmethod
    def _merge_object(
        cls,
        scrape_obj: DBModel,
        *,
        existing: DBModel | None = None,
    ) -> tuple[MergeResult[Any], DBModel]:
        if existing is None:
            db_obj = cls.get_existing(scrape_obj)
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
