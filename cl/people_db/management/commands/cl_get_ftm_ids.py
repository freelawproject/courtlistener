import os
import pickle
from collections import defaultdict

import requests
from django.conf import settings
from django.utils.timezone import now

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.scorched_utils import ExtraSolrInterface
from cl.people_db.import_judges.courtid_levels import courtid2statelevel
from cl.people_db.models import Person

leveldict = {
    "H": "J",  # State Supreme Court
    "M": "K",  # State Appellate Court
    "L": "D",  # Lower Court
}

url_template = (
    "http://api.followthemoney.org/?"
    "f-core=1&"
    "c-exi=1&"
    "gro=c-t-id&"
    "mode=json&"
    "APIKey={key}&"
    "s={state}&"
    "c-r-ot={level}&"
    "y={year}"
)


def make_dict_of_ftm_eids(use_pickle=True):
    """Build up a dictionary mapping jurisdiction IDs to candidates in those
    locations
    """
    pickle_location = "/tmp/eid_lists.pkl"
    if use_pickle:
        if os.path.isfile(pickle_location):
            with open(pickle_location, "r") as f:
                logger.info(
                    "Loading pickled candidate list. Read the command "
                    "documentation if this is not desired."
                )
                return pickle.load(f)
        else:
            logger.info("Unable to find pickle file.")

    candidate_eid_lists = defaultdict(list)

    for courtid, (state, level) in courtid2statelevel.items():
        if level != "H":
            # We only want high courts.
            continue
        for year in range(1989, 2017):
            url = url_template.format(
                key=settings.FTM_KEY,
                state=state,
                level=leveldict[level],
                year=year,
            )
            logger.info(f"Getting url at: {url}")
            data = requests.get(url, timeout=30).json()

            if data["records"] == ["No Records"]:
                logger.info(
                    f"  No records found in court {courtid} and year {year}."
                )
                continue
            logger.info(
                "  Found %s records in court %s and year %s"
                % (len(data["records"]), courtid, year)
            )

            for item in data["records"]:
                # add an eid, name, year tuple to this court's list
                candidate_eid_lists[courtid].append(
                    {
                        "eid": item["Candidate_Entity"]["id"],
                        "name": item["Candidate_Entity"]["Candidate_Entity"],
                        "total": float(item["Total_$"]["Total_$"]),
                        "year": year,
                    }
                )

    if use_pickle:
        with open(pickle_location, "w") as f:
            logger.info(f"Creating pickle file at: {pickle_location}")
            pickle.dump(candidate_eid_lists, f)
    return candidate_eid_lists


def clear_old_values(do_it, debug):
    """Clear out the old values in the ftm fields. If debug or do_it is False,
    don't clear the values.
    """
    if not do_it or debug:
        return
    logger.info("Clearing out all old values in FTM fields.")
    Person.objects.all().update(
        date_modified=now(), ftm_eid="", ftm_total_received=None
    )


def print_stats(match_stats, candidate_eid_lists):
    """Print the stats."""
    logger.info("#########")
    logger.info("# Stats #")
    logger.info("#########")
    logger.info("Finished matching judges:")
    for k, v in match_stats.items():
        logger.info(f" - {v} had {k} matches")
    ftm_judge_count = 0
    for v in candidate_eid_lists.values():
        ftm_judge_count += len(v)
        logger.info(
            f"There were {ftm_judge_count} judges in FTM that we matched against."
        )


def update_judges_by_solr(candidate_id_map, debug):
    """Update judges by looking up each entity from FTM in Solr."""
    with requests.Session() as session:
        conn = ExtraSolrInterface(
            settings.SOLR_PEOPLE_URL, http_connection=session, mode="r"
        )
        match_stats = defaultdict(int)
        # These IDs are ones that cannot be updated due to being identified as
        # problematic in FTM's data.
        denylisted_ips = defaultdict(set)
        for court_id, candidate_list in candidate_id_map.items():
            for candidate in candidate_list:
                # Look up the candidate in Solr.
                logger.info(f"Doing: {candidate['name']}")
                name = (
                    " AND ".join(
                        [
                            word
                            for word in candidate["name"].split()
                            if len(word) > 1
                        ]
                    )
                ).replace(",", "")
                results = (
                    conn.query()
                    .add_extra(
                        **{
                            "caller": "ftm_update_judges_by_solr",
                            "fq": [
                                f"name:({name})",
                                f"court_exact:{court_id}",
                                # This filters out Sr/Jr problems by insisting on recent
                                # positions. 1980 is arbitrary, based on testing.
                                "date_start:[1980-12-31T23:59:59Z TO *]",
                            ],
                            "q": "*",
                        }
                    )
                    .execute()
                )

                if len(results) == 0:
                    match_stats[len(results)] += 1
                    logger.info("Found no matches.")

                elif len(results) == 1:
                    match_stats[len(results)] += 1
                    logger.info(f"Found one match: {results[0]['name']}")

                    # Get the person from the DB and update them.
                    pk = results[0]["id"]
                    if pk in denylisted_ips:
                        continue
                    p = Person.objects.get(pk=pk)
                    if p.ftm_eid:
                        if p.ftm_eid != candidate["eid"]:
                            logger.info(
                                "  Found values in ftm database fields. "
                                "This indicates a duplicate in FTM."
                            )

                            denylisted_ips[p.pk].add(candidate["eid"])
                            denylisted_ips[p.pk].add(p.ftm_eid)
                            p.ftm_eid = ""
                            p.ftm_total_received = None
                        else:
                            logger.info(
                                "Found values with matching EID. Adding "
                                "amounts, since this indicates multiple "
                                "jurisdictions that the judge was in."
                            )
                            p.ftm_total_received += candidate["total"]
                        if not debug:
                            p.save()
                    else:
                        # No major problems. Proceed.
                        p.ftm_eid = candidate["eid"]
                        p.ftm_total_received = candidate["total"]
                        if not debug:
                            p.save()

                elif len(results) > 1:
                    match_stats[len(results)] += 1
                    logger.info(f"  Found more than one match: {results}")

        print_stats(match_stats, candidate_id_map)
        logger.info(f"Denylisted IDs: {denylisted_ips}")


class Command(VerboseCommand):
    help = (
        "Use the Follow the Money API to lookup judges by name and "
        "jurisdiction. Once looked up, save the ID to the DB."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Don't change the data.",
        )
        parser.add_argument(
            "--dont-use-pickle",
            action="store_false",
            default=True,
            help="Don't use a pickle file if one exists.",
        )
        parser.add_argument(
            "--clear-old-values",
            action="store_true",
            default=False,
            help="Clear out the old values before beginning.",
        )

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        candidate_id_map = make_dict_of_ftm_eids(options["dont_use_pickle"])
        clear_old_values(options["clear_old_values"], options["debug"])
        update_judges_by_solr(candidate_id_map, debug=options["debug"])
