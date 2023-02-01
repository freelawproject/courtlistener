import itertools
import json
import pathlib

import requests
from bs4 import BeautifulSoup
from django.core.management import BaseCommand
from juriscraper.lib.string_utils import harmonize, titlecase

from cl.corpus_importer.management.commands.harvard_opinions import \
    parse_extra_fields, validate_dt
from cl.lib.string_diff import get_cosine_similarity
from cl.people_db.lookup_utils import extract_judge_last_name

from cl.search.models import OpinionCluster


def merge_overlapping_data(opinion_cluster, json_harvard):
    # fields to get from json
    basic_fields_from_json_harvard = ["decision_date", "name",
                                      "name_abbreviation",
                                      "docket_number"]

    # fields to prepare from json
    short_fields_from_json_harvard = ["attorneys", "disposition", "otherdate",
                                      "seealso"]

    # fields to prepare from json
    long_fields_from_json_harvard = [
        "syllabus",
        "summary",
        "history",
        "headnotes",
        "correction",
    ]

    # Get data from json using specified fields
    additional_data = {}
    for f in basic_fields_from_json_harvard:
        additional_data[f] = json_harvard.get(f, "")

    # Get data from json file
    case_body = json_harvard["casebody"]["data"]
    soup = BeautifulSoup(case_body, "lxml")
    short_data = parse_extra_fields(soup, short_fields_from_json_harvard,
                                    False)
    long_data = parse_extra_fields(soup, long_fields_from_json_harvard, True)

    # Prepare judges list
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
    judges = titlecase(judges)

    # Add judges to harvard dict, this also contains author list
    additional_data["judges"] = judges

    # Combine all data into one dict
    harvard_data = dict({**additional_data, **short_data, **long_data})

    # key in json file: field name in CL
    MAP_FIELDS = {"decision_date": "date_filed",
                  "name": "case_name_full",
                  "name_abbreviation": "case_name"}
    harvard_reformat_data = dict()

    # rename keys to match cl field names
    for k, v in harvard_data.items():
        try:
            # Change key name
            harvard_reformat_data[MAP_FIELDS[
                k]] = harvard_data.get(k)
        except KeyError:
            # Keep key the same
            harvard_reformat_data[k] = harvard_data.get(k)

    if "date_filed" in harvard_reformat_data:
        # Convert date string to date object
        date_filed, is_approximate = validate_dt(
            harvard_reformat_data.get("date_filed"))
        harvard_reformat_data["date_filed"] = date_filed
        harvard_reformat_data[
            "date_filed_is_approximate"] = is_approximate

    # Remove empty or none values from json harvard
    harvard_reformat_data = {k: v for k, v in
                             harvard_reformat_data.items() if
                             v != "" or v is None}

    # Get cluster values as dict
    cluster_values = opinion_cluster.__dict__.copy()

    for f in ["id", "date_created", "date_modified", "docket_id",
              "slug", "scdb_id", "scdb_decision_direction",
              "scdb_votes_majority", "scdb_votes_minority",
              "nature_of_suit", "posture", "precedential_status",
              "date_blocked", "blocked", "filepath_json_harvard",
              "citation_count", "_state"]:
        # Remove unneeded values from cluster object dict
        del cluster_values[f]

    # Remove empty or none values from cluster dict
    cluster_values = {k: v for k, v in cluster_values.items() if
                      v != "" or v is None}

    # Get common keys between dicts, we only need to care about these
    common_keys = harvard_reformat_data.keys() & cluster_values.keys()

    # dict to store data to update in cluster
    update_data = dict()

    for key in common_keys:

        cl_data = cluster_values.get(key)
        harvard_data = harvard_reformat_data.get(key)

        if key in ["case_name_full", "case_name"]:
            # prepare harvard case name to check if names are the same
            harvard_data = harmonize(harvard_data)

        if cl_data == harvard_data:
            # Data is the same
            continue
        else:
            if key in ["case_name_full", "case_name"]:
                # TODO pick longer name?
                if len(harvard_data) > len(cl_data):
                    update_data[key] = harvard_data

            if key in long_fields_from_json_harvard:
                # Do some text comparison
                similarity = get_cosine_similarity(harvard_data,
                                                   cl_data)
                print(f"{key} similarity: {similarity}")
                if similarity < 0.9:
                    # which one is best? the longest?
                    if len(harvard_data) > len(cl_data):
                        update_data[key] = harvard_data

            if key in ["date_filed"]:
                # Which date is better?
                if "date_filed_is_approximate" in harvard_reformat_data:
                    date_filed_is_approximate = harvard_reformat_data.get(
                        "date_filed_is_approximate", False)
                    if not date_filed_is_approximate:
                        # if date filed is not approximate, means we have an
                        # exact date, then update the value
                        update_data[key] = harvard_data

            if key in ["judges"]:
                # let's normalize cl data, if it is already normalized, we will
                # get similar string, if not, then this is a good chance to
                # do it and then compare
                judges_last_names = [extract_judge_last_name(cl_data)]
                # Flatten and dedupe list of judges
                judges = ", ".join(
                    sorted(
                        list(set(itertools.chain.from_iterable(
                            judges_last_names)))
                    )
                )
                cl_data = titlecase(judges)
                similarity = get_cosine_similarity(harvard_data, cl_data)
                print("Judges similarity", similarity)
                if 0.51 <= similarity <= 0.81:
                    # Contains some judge names but not all of them, update
                    # data with normalized judges names
                    update_data[key] = harvard_data

            if type(cl_data) == bool and type(harvard_data) == bool:
                # generic case when bool value changes
                update_data[key] = harvard_data

            if type(cl_data) == str and type(harvard_data) == str:
                # generic case when both values are strings, like attorneys
                # field which not require a special process
                if len(harvard_data) > len(cl_data):
                    update_data[key] = harvard_data

    if update_data:
        print("update dict:", update_data)
        print("Updating opinion cluster....")
        OpinionCluster.objects.filter(pk=opinion_cluster.pk).update(
            **update_data)


def read_json(cluster: OpinionCluster, local: bool = False):
    if cluster.filepath_json_harvard:
        if local:
            path = pathlib.PurePath(str(cluster.filepath_json_harvard))
            ia_url = f"https://archive.org/download/{path.parent.name}/{path.name}"
            return requests.get(ia_url, timeout=100).json()
        else:
            return json.load(cluster.filepath_json_harvard)
    return None


def start_merger(cluster_id):
    opinion_cluster = OpinionCluster.objects.get(pk=cluster_id)
    print("opinion_cluster", opinion_cluster)

    harvard_data = read_json(opinion_cluster, local=True)
    if harvard_data:
        merge_overlapping_data(opinion_cluster, harvard_data)


class Command(BaseCommand):
    help = "Hello"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--cluster-id",
            type=str,
            help="The cluster id to merge",
            required=False,
        )

    def handle(self, *args, **options):
        start_merger(cluster_id=options["cluster_id"])

        # for cid in ids:
        #     cl_id = cid[0]
        #     ia_url = cid[1]
        #
        #     call_command('clone_from_cl', "--type=search.OpinionCluster",
        #                  f"--id={cl_id}")
        #
        #     opinion_cluster = OpinionCluster.objects.filter(pk=cl_id)
        #
        #     ia_data = requests.get(ia_url, timeout=100).json()
        #
        #     merge_overlapping_data(opinion_cluster, ia_data)
