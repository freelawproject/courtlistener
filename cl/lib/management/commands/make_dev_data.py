from django.core.management.base import CommandParser

from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.factories import PersonFactory, PersonWithChildrenFactory
from cl.recap.factories import FjcIntegratedDatabaseFactory
from cl.search.factories import (
    CourtFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    DocketWithChildrenFactory,
    OpinionClusterWithParentsFactory,
    OpinionWithParentsFactory,
    ParentheticalWithParentsFactory,
)
from cl.users.factories import SuperUserFactory, UserFactory

FACTORIES = {
    # Search app
    100: CourtFactory,
    101: DocketFactory,
    102: OpinionClusterWithParentsFactory,
    103: OpinionWithParentsFactory,
    104: DocketEntryWithParentsFactory,
    105: ParentheticalWithParentsFactory,
    106: FjcIntegratedDatabaseFactory,
    # People DB app
    200: PersonFactory,
    201: PersonWithChildrenFactory,
    # Users
    300: UserFactory,
    301: SuperUserFactory,
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

    def handle(self, *args, **options) -> None:
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
            DocketWithChildrenFactory.create_batch(count)
            logger.info(f"Making {count} judges and all their positions")
            PersonWithChildrenFactory.create_batch(count)
            logger.info(f"Making {count} users and super users")
            UserFactory.create_batch(count)
            SuperUserFactory.create_batch(count)
        else:
            # The user requested something specific. Build that thing and all
            # the parents above it.
            for object_type in options["object_types"]:
                Factory = FACTORIES[object_type]
                logger.info(
                    f"Making {count} items and their dependant parents using "
                    f"object type #{object_type}: {Factory}"
                )
                Factory.create_batch(count)
