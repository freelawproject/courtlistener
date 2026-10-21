import argparse
import logging
import os
import re
from argparse import Namespace
from typing import (
    Any,
    ClassVar,
    Literal,
    NotRequired,
    TypedDict,
    cast,
    final,
)

from django.core.management import BaseCommand, CommandError
from pydantic_settings import BaseSettings, CliApp
from pydantic_settings.sources.providers.cli import (
    CliSettingsSource,
)

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


class AbstractCommand[S: BaseSettings](BaseCommand):
    """Base class to allow defining Django management command arguments as Pydantic models.

    Why? This allows a number of advantages over the default way of defining commands:
        1. Arguments use attribute access instead of untyped dict access allowing better type checking
        2. Defining command arguments as attributes is less verbose than Django's default
        3. Pydantic offers better validation of argument values

    Usage:
        Arguments are defined in a class-scoped `Argument` class inheriting from pydantic_settings `BaseSettings`.

        ```
        class CoolCommand(AbstractCommand):
            help = "Command help"

            class Arguments(BaseSettings):
                flag: bool = Field(
                    alias="flag-store-true",
                )
                '''Help text'''
                not_required: str = Field(
                    alias="has-default",
                    default="meow",
                )
                go_valks: str
                '''Cheering for the Golden State Valkyries is required'''

            def run(self, arguments: Arguments):
                print(f"{self.go_valks}!")
        ```

        Command help text will be pulled from the class docstring. Help text for individual arguments is pulled from the docstrings.

        Flags (`action="store_true"` or `action="store_false"` when using argparse) are automatically created from
        boolean fields based on their default values.

        Instance variable names containing underscores will be automatically converted to kebab case as arguments.

        The `run` method is used instead of `handle` and is passed the parsed arguments.

    Details:
        If a field is marked as a boolean with a default, it will be sent to `ArgumentParser.add_argument` with
        a `"store_true"` or `"store_false"` action depending on the value of the default. This can be overridden
        by annotating the field as something like `bool | None`.

        Iterable type fields like lists and sets will be sent to `ArgumentParser.add_argument` with `"+"` or `"*"`
        as their `nargs` value depending on whether or not they are required (required->"+", not required->"*").

        Arguments will be automatically registered with Django's `add_arguments` using pydantic_settings'
        `CliSettingsSource` with the following configuration:
            - `cli_ignore_unknown_args=True`
            - `cli_use_class_docs_for_groups=True`
            - `cli_implicit_flags=True`
            - `cli_enforce_required=True`
            - `cli_exit_on_error=False`
            - `cli_kebab_case=True`
    """

    Arguments: ClassVar[type]
    """The `BaseSettings` class defining this command's arguments."""
    _cli_settings_source: CliSettingsSource | None = None

    @classmethod
    def __init_subclass__(cls, *args, **kwargs) -> None:
        doc = cls.__doc__ or ""
        cls.help = re.sub(r"\w\n\s+", " ", doc.replace("\n\n", "\n"))
        super().__init_subclass__(*args, **kwargs)

    @final
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        Arguments = getattr(self.__class__, "Arguments", None)
        if not isinstance(Arguments, type) or not issubclass(
            Arguments, BaseSettings
        ):
            logger.warning(
                "The Arguments class must be provided and must be a subclass of pydantic_settings' BaseSettings class"
            )
            return

        self._cli_settings_source = CliSettingsSource(
            Arguments,
            root_parser=parser,
            cli_ignore_unknown_args=True,
            cli_use_class_docs_for_groups=True,
            cli_implicit_flags=True,
            cli_enforce_required=True,
            cli_exit_on_error=False,
            cli_kebab_case=True,
        )

    @final
    def handle(self, *args: Any, **kwargs: Any) -> None:
        if self._cli_settings_source is None:
            return

        Arguments = getattr(self.__class__, "Arguments", None)
        if not isinstance(Arguments, type) or not issubclass(
            Arguments, BaseSettings
        ):
            return

        # Undo the stuff Django did to give us our arguments
        parsed = Namespace(args=args, **kwargs)
        arguments = CliApp.run(
            Arguments,
            cli_args=parsed,
            cli_settings_source=self._cli_settings_source,
        )

        self.run(cast(S, arguments))

    def run(self, arguments: S) -> None:
        raise NotImplementedError("Commands must implement the run method")
