from django.db import transaction
from django.db.models import Count

from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.models import Attorney
from cl.people_db.models import AttorneyOrganizationAssociation as AttyOrgAss
from cl.people_db.models import Role
from cl.search.models import Docket


@transaction.atomic
def clone_attorney(orig_atty_id, atty, docket):
    # Clone the atty, then swap it in. After this point, the atty
    # variable is the *NEW* attorney, no longer the one one. Be
    # careful which you use for lookups and assignment.
    atty.id = None
    atty.save()
    logger.info(f"Created new attorney: {atty}")

    roles_for_docket = Role.objects.filter(
        attorney_id=orig_atty_id, docket=docket
    )
    logger.info(
        "Got %s roles for this attorney on docket %s. Remapping "
        "them all." % (roles_for_docket.count(), docket)
    )
    roles_for_docket.update(attorney=atty)

    # The attorney is now in place for the docket and party. Remap
    # their organizational information too.
    atty_orgs_for_docket = AttyOrgAss.objects.filter(
        docket=docket, attorney_id=orig_atty_id
    )
    logger.info(
        "Got %s organization associations on this docket for this "
        "attorney." % atty_orgs_for_docket.count()
    )
    atty_orgs_for_docket.update(attorney=atty)


class Command(VerboseCommand):
    help = "Split attorneys that are currently across multiple dockets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=0,
            help="The number of attorneys to do. Default is to do all of them.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)

        # Get attorneys that have roles on more than one docket
        roles = (
            Role.objects.values("attorney_id")
            .annotate(Count("id"))
            .order_by()
            .filter(id__count__gt=1)
        )
        logger.info(
            f"Got {roles.count()} attorneys that are on more than one docket."
        )

        # That returns a list of dictionaries like:
        # {'attorney_id': 1, 'id__count': 2}
        for i, role in enumerate(roles):
            if i >= options["count"] > 0:
                break
            orig_atty_id = role["attorney_id"]
            atty = Attorney.objects.get(pk=orig_atty_id)
            dockets = (
                Docket.objects.filter(role__attorney=atty)
                .order_by("date_created")
                .distinct()
            )
            logger.info(
                f"Got {dockets.count()} dockets for attorney {atty}. Cloning them all."
            )

            for docket in dockets[1:]:
                clone_attorney(orig_atty_id, atty, docket)
