import itertools
import json
import logging

from bs4 import BeautifulSoup
from juriscraper.lib.string_utils import titlecase

from cl.lib.command_utils import VerboseCommand
from cl.people_db.lookup_utils import extract_judge_last_name
from cl.search.models import OpinionCluster, Docket


def judges_in_harvard(cluster, harvard):
    """We certainly need to rethink how we are going to handle judge names
    # we have an example where a judge has an h in one but not hte ohter but
    we reduce that down to just last names.   do we wnat to do that...
    should we identify how many judges we have.....its also confusing.

    :param cluster:
    :type cluster:
    :param harvard:
    :type harvard:
    :return:
    :rtype:
    """
    if not cluster.judges:
        """Merge in judges if judges exist"""
        return True

    case_body = harvard["casebody"]["data"]

    soup = BeautifulSoup(case_body, "lxml")

    judge_list = [
        extract_judge_last_name(x.text) for x in soup.find_all("judges")
    ]
    author_list = [
        extract_judge_last_name(x.text) for x in soup.find_all("author")
    ]
    # Flatten and dedupe list of judges
    judges = ", ".join(
        sorted(
            list(set(itertools.chain.from_iterable(judge_list + author_list)))
        )
    )
    harvard_judges = titlecase(judges)
    cl_judges = titlecase(", ".join(extract_judge_last_name(cluster.judges)))

    if harvard_judges == cl_judges:
        """No need to do anything because the names already match"""
        return True
    else:
        """here is our decision tree for what to do with judge names"""
        print(judges, cluster.judges)
        ex_cl = titlecase(", ".join(extract_judge_last_name(cluster.judges)))
        print(ex_cl)

        return judges == cluster.judges


def read_json(cluster: OpinionCluster):
    """Load json from filepath_json_harvard field
    """
    return json.load(cluster.filepath_json_harvard)


def handle_names(cluster, harvard):
    """"""
    cl_short_name = cluster.case_name_short
    cl_medium_name = cluster.case_name
    cl_long_name = cluster.case_name_full

    hvd_short = harvard['name_abbreviation']
    hvd_long = harvard['name']

    """Make super smart decision about how to handle naming convetions"""
    # if cl_short_name == None:


def handle_judge_names(cluster, harvard):
    """"""
    judges = cluster.judges

    hvd_short = harvard['name_abbreviation']
    hvd_long = harvard['name']

    """Make super smart decision about how to handle naming convetions"""
    # if cl_short_name == None:


def merge_opinion(cluster):
    """"""
    harvard_data = read_json(cluster)

    # Maybe convert cluster data into dict with model_to_dict()
    # Rename fields in harvard data to match cluster field names
    # Use a loop to compare and store only the fields that are different
    # Use a dict to update cluster object
    print(harvard_data)


def start_merger(cluster_ids):
    """Prepare cluster queryset and start merge process
    """
    if cluster_ids:
        clusters = OpinionCluster.objects.filter(id__in=cluster_ids).exclude(
            filepath_json_harvard="")
    else:
        sources_without_harvard = [
            source[0]
            for source in Docket.SOURCE_CHOICES
            if "Harvard" not in source[1]
        ]
        clusters = OpinionCluster.objects.filter(
            docket__source__in=sources_without_harvard
        ).exclude(
            filepath_json_harvard="")

    for cluster in clusters:
        merge_opinion(cluster=cluster)


class Command(VerboseCommand):
    help = "Download and save Harvard corpus on IA to disk."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cluster-ids",
            dest="ids",
            nargs="+",
            type=int,
            help="The cluster id or ids to merge",
            required=False,
        )
        parser.add_argument(
            "--no-debug",
            action="store_true",
            help="Turn off debug logging",
        )

    def handle(self, *args, **options):
        if options["no_debug"]:
            logging.disable(logging.DEBUG)
        start_merger(cluster_ids=options.get("ids", []))
