from asgiref.sync import async_to_sync
from juriscraper.lib.string_utils import titlecase

from cl.lib.command_utils import VerboseCommand, logger
from cl.people_db.lookup_utils import (
    extract_judge_last_name,
    lookup_judge_by_last_name,
    lookup_judges_by_last_name_list,
)
from cl.search.models import Opinion, OpinionCluster


def normalize_authors_in_opinions():
    """Normalize author_str in opinions"""

    # Get opinions that have no author object and have author_str
    opinions_with_author_str = Opinion.objects.exclude(
        author__isnull=False
    ).exclude(author_str="")
    for opinion in opinions_with_author_str.iterator():
        date_filed = opinion.cluster.docket.date_filed
        court_id = opinion.cluster.docket.court_id
        # Search for person, living or deceased
        person = async_to_sync(lookup_judge_by_last_name)(
            opinion.author_str, court_id, date_filed, False
        )

        if not person:
            logger.warning(
                f"Can't find person with this last name: "
                f"{opinion.author_str} in opinion id: {opinion.pk}"
            )
        else:
            # Set person object to author
            opinion.author = person
            opinion.save()
            logger.info(f"Author updated in opinion id: {opinion.pk}")


def normalize_panel_in_opinioncluster():
    """Normalize panel in opinion cluster object"""

    # Get opinion cluster that have no panel objects and have judges_str
    opinion_clusters_with_judges_str = OpinionCluster.objects.exclude(
        panel__isnull=False
    ).exclude(judges__exact="")
    for opinion_cluster in opinion_clusters_with_judges_str.iterator():
        date_filed = opinion_cluster.date_filed
        court_id = opinion_cluster.docket.court_id

        # Convert judges last name string to list
        last_name_list = opinion_cluster.judges.split(", ")

        # Sometimes the full names are stored in the judges field, we only
        # need the last names
        prepared_last_name_list = [
            titlecase("".join(extract_judge_last_name(y)))
            for y in last_name_list
        ]

        # Search for judges as Person objects
        people = async_to_sync(lookup_judges_by_last_name_list)(
            prepared_last_name_list, court_id, date_filed, False
        )

        if not people:
            logger.warning(
                f"Can't find these people/person: {opinion_cluster.judges} in "
                f"opinion cluster id: {opinion_cluster.pk}"
            )

        if people:
            for person in people:
                # Add each person to panel
                opinion_cluster.panel.add(person)
            logger.info(
                f"Panel updated in opinion cluster id: {opinion_cluster.pk}"
            )


class Command(VerboseCommand):
    help = (
        "Populate author field in opinions using author_str field and "
        "populate panel in opinion clusters using judges field. "
    )

    def handle(self, *args, **options):
        normalize_authors_in_opinions()
        normalize_panel_in_opinioncluster()
