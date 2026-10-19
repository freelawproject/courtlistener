import argparse
import logging
import os
import typing
from abc import ABC, abstractmethod
from collections.abc import Iterable
from copy import copy
from typing import (
    Any,
    ClassVar,
    Literal,
    NotRequired,
    TypedDict,
    final,
)

from django.core.management import BaseCommand, CommandError
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from cl.lib.juriscraper_utils import get_module_by_court_id

logger = logging.getLogger(__name__)


class VerboseCommand(BaseCommand):
    def handle(self, *args, **options):
        verbosity = options.get("verbosity")
        if not verbosity:
            logger.setLevel(logging.WARN)
        elif verbosity == 0:
            logger.setLevel(logging.WARN)
        elif verbosity == 1:  # default
            logger.setLevel(logging.INFO)
        elif verbosity > 1:
            logger.setLevel(logging.DEBUG)
            # This will make juriscraper's logger accept most logger calls.
            juriscraper_logger = logging.getLogger("juriscraper")
            juriscraper_logger.setLevel(logging.DEBUG)


class ScraperCommand(VerboseCommand):
    """Base class for cl.scrapers commands that use Juriscraper

    Implements the `--courts` argument to lookup for a Site object
    """

    # To be used on get_module_by_court_id
    # Defined by inheriting classes
    juriscraper_module_type = ""

    def add_arguments(self, parser):
        parser.add_argument(
            "--courts",
            dest="court_id",
            metavar="COURTID",
            type=lambda s: (
                s
                if "." in s
                else get_module_by_court_id(s, self.juriscraper_module_type)
            ),
            required=True,
            help=(
                "The court(s) to scrape and extract. One of: "
                "1. a python module or package import from the Juriscraper library, e.g."
                "'juriscraper.opinions.united_states.federal_appellate.ca1' "
                "or simply 'juriscraper.opinions' to do all opinions."
                ""
                "2. a court_id, to be used to lookup for a full module path"
                "An error will be raised if the `court_id` matches more than "
                "one module path. In that case, use the full path"
            ),
        )


class _ParserKWargs(TypedDict):
    action: NotRequired[Literal["store_true", "store_false"]]
    nargs: NotRequired[Literal["*", "+"]]
    required: bool
    help: NotRequired[str]
    dest: str


class CommandUtils:
    """A mixin to give some useful methods to sub classes."""

    @staticmethod
    def ensure_file_ok(file_path):
        """Check to make sure that a file path exists and is valid."""
        if not os.path.exists(file_path):
            raise CommandError(f"Unable to find file at {file_path}")
        if not os.access(file_path, os.R_OK):
            raise CommandError(f"Unable to read file at {file_path}")


class AbstractCommand(BaseCommand, BaseModel, ABC):
    """Base class to allow defining Django management command inputs as Pydantic models.

    Why? This allows a number of advantages over the default way of defining commands:
        1. Arguments use attribute access instead of untyped dict access allowing better type checking
        2. Defining command arguments as attributes is less verbose than Django's default
        3. Pydantic offers better validation of argument values

    Usage:
        ```
        class CoolCommand(AbstractCommand):
            help = "Command help"

            flag: bool = Field(
                alias="flag-store-true",
                default=False,
                description="Help text",
            )
            not_required: str = Field(
                alias="has-default",
                default="meow",
            )
            go_valks: str = Field(
                alias="go-valks",
                description="Cheering for the Golden State Valkyries is required",
            )

            def run(self):
                print(f"{self.go_valks}!")
        ```

    Details:
        If a field is marked as a boolean with a default, it will be sent to `ArgumentParser.add_argument` with
        a `"store_true"` or `"store_false"` action depending on the value of the default. This can be overridden
        by annotating the field as something like `bool | None`.

        Iterable type fields like lists and sets will be sent to `ArgumentParser.add_argument` with `"+"` or `"*"`
        as their `nargs` value depending on whether or not they are required (required->"+", not required->"*").

        The `run` method is used instead of `handle`.
    """

    __aliased__: ClassVar[dict[str, FieldInfo]] = {}
    """Dictionary mapping aliases to their associated FieldInfo objects"""

    @classmethod
    def __init_subclass__(cls):
        cls.__aliased__ = copy(cls.__aliased__)
        for name, info in cls.model_fields.items():
            if (alias := info.alias) is not None:
                cls.__aliased__[alias] = info
        super().__init_subclass__()

    def __init__(*args: Any, **kwargs: Any): ...

    @final
    def add_arguments(self, parser: argparse.ArgumentParser):
        for name, info in self.__class__.model_fields.items():
            required = info.is_required()
            arg = name if info.alias is None else info.alias
            config: _ParserKWargs = {
                "dest": arg,
                "required": required,
            }

            if (annotation := info.annotation) is not None:
                if isinstance(annotation, type):
                    if (
                        issubclass(annotation, Iterable)
                        and annotation is not str
                        and annotation is not dict
                    ):
                        config["nargs"] = "+" if required else "*"
                    elif annotation is bool and not required:
                        config["action"] = (
                            "store_false" if info.default else "store_true"
                        )
                else:
                    # pyrefly:ignore[bad-assignment] This is due to incorrect typing of Pydantic's FieldInfo
                    container: type[Any] | None = typing.get_origin(annotation)
                    if container is not None:
                        items = typing.get_args(annotation)
                        if (
                            len(items) == 1
                            and issubclass(container, Iterable)
                            and container is not dict
                        ):
                            config["nargs"] = "+" if required else "*"

            if (description := info.description) is not None:
                config["help"] = description

            parser.add_argument(
                f"--{arg.lower().replace('_', '-')}",
                **config,
            )

    @final
    def handle(self, *args: Any, **kwargs: Any):
        named = copy(kwargs)
        for name, value in list(named.items()):
            if value is None:
                info = self.__class__.__aliased__.get(
                    name, self.__class__.model_fields.get(name)
                )
                if (
                    info is not None
                    and not info.is_required()
                    and info.default is not None
                ):
                    del named[name]
        BaseModel.__init__(self, positional=args, **named)
        self.run()

    @abstractmethod
    def run(self): ...
