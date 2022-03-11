from typing import Iterable, Union

from django.core.management import CommandParser

from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.factories import PersonFactory
from cl.recap.factories import FjcIntegratedDatabaseFactory
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    DocketFactoryWithChildren,
    OpinionClusterFactoryWithParents,
    OpinionFactoryWithParents,
    ParentheticalFactoryWithParents,
)

FACTORIES = {
    0: CourtFactory,
    1: DocketFactory,
    2: OpinionClusterFactoryWithParents,
    3: OpinionFactoryWithParents,
    4: ParentheticalFactoryWithParents,
    5: PersonFactory,
    6: FjcIntegratedDatabaseFactory,
}
factories_str = "\n".join([f"{k}: {v}" for k, v in FACTORIES.items()])


class Command(VerboseCommand):
    help = "Create dummy data in your system for development purposes"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help=f"How many items to create",
        )
        parser.add_argument(
            "--object-types",
            type=int,
            nargs="+",
            required=False,
            help=f"Which type of objects do you want. Select by number from "
            f"(multiple numbers allowed, separated by spaces): "
            f"\n{factories_str}",
        )

    def handle(self, *args: str, **options: Union[int, Iterable]):
        super(Command, self).handle(*args, **options)
        count = options["count"]
        logger.info(
            f"Creating dummy data. Making at least {count} "
            f"objects of each type."
        )
        if options["object_types"] is None:
            # Just make a bit of everything. Start with a docket and build all
            # the children below it.
            logger.info(
                f"Making {count} dockets and all their dependent objects"
            )
            DocketFactoryWithChildren.create_batch(count)
        else:
            # The user requested something specific. Build that thing and all
            # the parents above it.
            for object_type in options["object_types"]:
                Factory = FACTORIES[object_type]
                logger.info(
                    f"Making {count} items and their depedent parents using "
                    f"object type #{object_type}: {Factory}"
                )
                Factory.create_batch(count)
