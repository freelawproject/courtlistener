import argparse
import time

from django.db import transaction
from django.db.models import Count

from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Opinion, OpinionCluster


def sort_harvard_opinions(options) -> None:
    """Sort harvard opinions

    We assume that harvard data is already ordered, we just need to fill
    the order field in each opinion

    The harvard importer created the opinions in order of appearance in the file

    :param options: dict of arguments passed to the command
    :return: None
    """

    skip_until = options.get("skip_until", None)
    limit = options.get("limit", None)

    # The filepath_json_harvard field can only be filled by the harvard importer,
    # this helps us confirm that it was imported from a Harvard json
    harvard_clusters = (
        OpinionCluster.objects.exclude(filepath_json_harvard="")
        .prefetch_related("sub_opinions")
        .annotate(opinions_count=Count("sub_opinions"))
        .filter(opinions_count__gt=1)
        .order_by("id")
    )
    if skip_until:
        harvard_clusters = harvard_clusters.filter(pk__gte=skip_until)

    if limit:
        harvard_clusters = harvard_clusters[:limit]

    for cluster in harvard_clusters:
        logger.info(f"Processing cluster id: {cluster}")
        opinion_order = 1
        any_update = False
        with transaction.atomic():
            # We need to make sure they are ordered by id
            for cluster_op in cluster.sub_opinions.all().order_by("id"):
                if cluster_op.type == Opinion.COMBINED:
                    continue
                cluster_op.ordering_key = opinion_order
                cluster_op.save()
                opinion_order = opinion_order + 1
                any_update = True
            if not any_update:
                # We want to know if you found anything unexpected, like for example
                # only having combined opinions
                logger.info(
                    f"No sub_opinions updated for cluster id: {cluster}"
                )
                continue
            logger.info(msg=f"Opinions reordered for cluster id: {cluster.id}")
            # Wait between each processed cluster to avoid issues with elastic
            time.sleep(options["delay"])


class Command(VerboseCommand):
    help = "Add ordering Key for sub opinions"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def valid_actions(self, s):
        if s.lower() not in self.VALID_ACTIONS:
            raise argparse.ArgumentTypeError(
                "Unable to parse action. Valid actions are: %s"
                % (", ".join(self.VALID_ACTIONS.keys()))
            )

        return self.VALID_ACTIONS[s]

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-until",
            help="Specific cluster id to skip until",
            type=int,
            required=False,
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Number of files to sort",
            required=False,
        )
        parser.add_argument(
            "--action",
            type=self.valid_actions,
            required=True,
            help="The action you wish to take. Valid choices are: %s"
            % (", ".join(self.VALID_ACTIONS.keys())),
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.2,
            help="How long to wait to update each opinion (in seconds, allows "
            "floating numbers).",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        options["action"](options)

    VALID_ACTIONS = {"sort-harvard": sort_harvard_opinions}
