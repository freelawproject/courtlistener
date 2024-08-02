from django.db.models import Count, Q

from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import SOURCES, Opinion, OpinionCluster


def sort_harvard_opinions(options) -> None:
    """Sort harvard opinions

    We assume that harvard data is already ordered, we just need to fill
    the order field in each opinion

    The harvard importer created the opinions in order of appearance in the file

    :param options: dict of arguments skip until and limit if given
    :return: None
    """

    skip_until = options.get("skip_until", None)
    limit = options.get("limit", None)

    base_filter = (
        OpinionCluster.objects.exclude(filepath_json_harvard="")
        .annotate(opinions_count=Count("sub_opinions"))
        .filter(opinions_count__gt=1)
    )

    if skip_until:
        base_filter &= Q(pk__gte=skip_until)

    harvard_clusters = (
        OpinionCluster.objects.annotate(opinions_count=Count("sub_opinions"))
        .filter(base_filter)
        .order_by("id")
    )
    if limit:
        harvard_clusters = harvard_clusters[:limit]

    for cluster in harvard_clusters:
        logger.info(f"Processing cluster id: {cluster}")
        sub_opinions = cluster.sub_opinions.exclude(
            type=Opinion.COMBINED,
        ).order_by("id")
        if not sub_opinions:
            logger.info(
                f"No sub_opinions left to order for cluster id: {cluster}"
            )
            continue
        for opinion_order, cluster_op in enumerate(sub_opinions, start=1):
            cluster_op.ordering_key = opinion_order
            cluster_op.save()
        logger.info(msg=f"Opinions reordered for cluster id: {cluster.id}")


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

    def handle(self, *args, **options):
        super().handle(*args, **options)
        options["action"](options)

    VALID_ACTIONS = {"sort-harvard": sort_harvard_opinions}
