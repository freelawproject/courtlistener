import logging
import types
from abc import ABC
from collections.abc import Callable, Iterable
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

from cl.corpus_importer.state.utils import MergeResult

logger = logging.getLogger(__name__)


class AttributeSpecification(ABC): ...


class MapInput[ScrapedData, Output](AttributeSpecification):
    def __init__(
        self, map: Callable[[ScrapedData], Output] | None = None
    ) -> None:
        if map is not None:
            self._map: Callable[[ScrapedData], Output | None] = map

    def map(self, i: ScrapedData) -> Output | None:
        return self._map(i)


class InputField[ScrapedData, Output](MapInput[ScrapedData, Output]):
    def __init__(self, path: str, default: Output | None = None) -> None:
        super().__init__()
        self.path: list[str] = [p for p in path.split(".") if p]
        self.default: Output | None = default
        if not self.path:
            raise ValueError("Path must not be empty")

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


class NeverMapping[ScrapedData, T](MapInput[ScrapedData, T]):
    @override
    def map(self, i: ScrapedData) -> None:
        return None


class AttributeMerger[ScrapedData, DBModel: Model, T]:
    def __init__(
        self, name: str, specifications: list[AttributeSpecification]
    ) -> None:
        map = None
        self.name: str = name
        for spec in specifications:
            match spec:
                case MapInput() as m:
                    if map is None:
                        _map = m
                    else:
                        raise ValueError(
                            "Only one mapping is allowed per attribute"
                        )
                case _:
                    raise TypeError(f"Unknown attribute specification {spec}")

        self._map: MapInput[ScrapedData, T] = (
            map or NeverMapping[ScrapedData, T]()
        )

    def get_value(self, i: ScrapedData) -> T | None:
        """Compute the value of an attribute from scraped data."""
        return self._map.map(i)

    def merge_values(self, scrape: DBModel, db: DBModel) -> T:
        """Merge the values of two attributes (scrape and DB) and return the merged value."""
        raise NotImplementedError


class RelatedMerger: ...


class Merger[ScrapedData, DBModel: Model](ABC):
    __attr_mergers__: list[AttributeMerger[ScrapedData, DBModel, Any]]
    __related_mergers__: ClassVar[list[RelatedMerger]]
    __model__: type[Model]
    __default_values__: ClassVar[dict[str, Any]] = {}
    _uses_natural_key: ClassVar[bool] = True
    atomic: ClassVar[bool] = False
    # I'd like to make this a ClassVar for static type checking, but that's not allowed for some reason
    existing: Iterable[str] | Callable[[DBModel], DBModel | None] = []

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        annotated: list[tuple[str, list[AttributeSpecification]]] = [
            (
                name,
                [
                    a
                    for a in hint.__metadata__
                    if isinstance(a, AttributeSpecification)
                ],
            )
            for name, hint in get_type_hints(cls, include_extras=True).items()
            if not name.startswith("_") and get_origin(hint) is Annotated
        ]

        cls.__attr_mergers__ = [
            AttributeMerger(name, specs) for name, specs in annotated
        ]
        cls.__related_mergers__ = []

        merger_base = next(
            (
                base
                for base in types.get_original_bases(cls)
                if get_origin(base) is Merger
            ),
            None,
        )
        if merger_base is None:
            raise TypeError(
                "Merger must be a subclass of Merger (I don't know how you managed to do this tbh)."
            )
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
        cls.__default_values__ = {
            field.name: getattr(cls, field.name)
            for field in cls.__model__._meta.fields
            if hasattr(cls, field.name)
        }

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
                f"Multiple objects found for natural key {cls.existing} in {i}"
            )

    @classmethod
    def merge(cls, i: ScrapedData) -> MergeResult[Any]:
        if not cls.validate(i):
            logger.error(f"Merger {cls.__name__} received invalid input: {i}")
            return MergeResult.failed(cls.__name__)
        obj = cast(
            DBModel,
            cls.__model__(
                **(
                    cls.__default_values__
                    | {am.name: am.get_value(i) for am in cls.__attr_mergers__}
                )
            ),
        )

        if cls.atomic:
            with transaction.atomic():
                result = cls._merge_object(obj)
        else:
            result = cls._merge_object(obj)

        if result.failed:
            cls.after(i, None, result)
        # TODO Merge children and relatives here
        return result

    @classmethod
    def _merge_object(cls, scrape_obj: DBModel) -> MergeResult[Any]:
        db_obj = cls.get_existing(scrape_obj)
        if db_obj is None:
            scrape_obj.save()
            return MergeResult.created(cls.__model__.__name__, scrape_obj.pk)

        update = False
        for am in cls.__attr_mergers__:
            scrape_value = getattr(scrape_obj, am.name)
            db_value = getattr(db_obj, am.name)
            merged_value = am.merge_values(scrape_value, db_value)
            if merged_value != db_value:
                setattr(db_obj, am.name, merged_value)
                update = True

        if update:
            db_obj.save()
            return MergeResult.updated(cls.__model__.__name__, db_obj.pk)
        return MergeResult.unnecessary()


# class InputField(MergerMapping):
#     path: list[str]
#
#     def __init__(self, path: str) -> None:
#         self.path = [p for p in path.split(".") if p]
#
#     @override
#     def map[Output](self, i: object, c: Output | None) -> Output:
#         if not self.path:
#             return i
#         current = i
#         for p in self.path:
#             if isinstance(current, dict) and p in current:
#                 current = current[p]
#             elif hasattr(current, p):
#                 current = getattr(current, p)
#             else:
#                 raise ValueError(f"Could not find {self.path} in {i}")
#         return current


# class TransformField(MergerMapping):
#     @override
#     def map(self, i: Any, c: Any) -> Any:
#         return i
