import os
import pickle
from collections import defaultdict

import requests
from django.conf import settings
from django.core.management import BaseCommand

from cl.lib.sunburnt import SolrInterface
from cl.people_db.import_judges.courtid_levels import courtid2statelevel
from cl.people_db.models import Person

leveldict = {
    'H': 'J',  # State Supreme Court
    'M': 'K',  # State Appellate Court
    'L': 'D',  # Lower Court
}

url_template = (
    'http://api.followthemoney.org/?'
    'f-core=1&'
    'c-exi=1&'
    'gro=c-t-id&'
    'mode=json&'
    'APIKey={key}&'
    's={state}&'
    'c-r-ot={level}&'
    'y={year}'
)


def make_dict_of_ftm_eids(use_pickle=True):
    """Build up a dictionary mapping jurisdiction IDs to candidates in those
    locations
    """
    pickle_location = '/tmp/eid_lists.pkl'
    if use_pickle:
        if os.path.isfile(pickle_location):
            with open(pickle_location, 'r') as f:
                print("Loading pickled candidate list. Read the command "
                      "documentation if this is not desired.")
                return pickle.load(f)
        else:
            print("Unable to find pickle file.")

    candidate_eid_lists = defaultdict(list)

    for courtid, (state, level) in courtid2statelevel.items():
        if level != 'H':
            # We only want high courts.
            continue
        for year in range(1989, 2017):
            url = url_template.format(
                key=settings.FTM_KEY,
                state=state,
                level=leveldict[level],
                year=year,
            )
            print("Getting url at: %s" % url)
            data = requests.get(url).json()

            if data['records'] == ['No Records']:
                print('  No records found in court %s and year %s.' % (
                    courtid,
                    year,
                ))
                continue
            print('  Found %s records in court %s and year %s' % (
                len(data['records']),
                courtid,
                year,
            ))

            for item in data['records']:
                # add an eid, name, year tuple to this court's list
                candidate_eid_lists[courtid].append({
                    'eid': item['Candidate_Entity']['id'],
                    'name': item['Candidate_Entity']['Candidate_Entity'],
                    'total': float(item['Total_$']['Total_$']),
                    'year': year,
                })

    if use_pickle:
        with open(pickle_location, 'w') as f:
            print("Creating pickle file at: %s" % pickle_location)
            pickle.dump(candidate_eid_lists, f)
    return candidate_eid_lists


def print_stats(match_stats, candidate_eid_lists):
    """Print the stats."""
    print("\n#########")
    print("# Stats #")
    print("#########")
    print("Finished matching judges:")
    for k, v in match_stats.items():
        print(" - %s had %s matches" % (v, k))
    ftm_judge_count = 0
    for v in candidate_eid_lists.values():
        ftm_judge_count += len(v)
    print("\nThere were %s judges in FTM that we matched "
          "against." % ftm_judge_count)


def update_judges(candidate_id_map, debug):
    """Iterate over the judges and update their information."""
    msg = '# Beginning process of updating judges. #'
    print("\n\n%s\n%s\n%s" % ('#' * len(msg), msg, '#' * len(msg)))

    match_stats = defaultdict(int)
    for person in Person.objects.all():
        print("\nDoing: %s" % person)
        judge_matches = []
        for position in person.positions.all():
            if not position.is_judicial_position:
                # We only care about judicial positions.
                continue
            if position.court is None:
                # If the position wasn't in a court, punt.
                continue
            if position.court.pk not in courtid2statelevel:
                # Either not a state court or the Court field is None.
                continue
            if courtid2statelevel[position.court.pk][1] != 'H':
                # We only want high courts
                continue

            judges_in_court = candidate_id_map[position.court.pk]

            # Check last name
            position_matches = []
            for judge in judges_in_court:
                # Match name by lowercasing and comparing the last, first name
                # combo.
                judge_name = judge['name'].lower()
                person_name = ('%s, %s' % (person.name_last,
                                           person.name_first)).lower()
                if judge_name.startswith(person_name):
                    position_matches.append(judge)

            for position_match in position_matches:
                existing_judge_match_eids = [j['eid'] for j in judge_matches]
                if position_match['eid'] not in existing_judge_match_eids:
                    # add the item.
                    judge_matches.append(position_match)

        # Save if there's only one unique match across all positions.
        if len(judge_matches) == 1:
            print("  Found one match: %s" % judge_matches[0])
            match_stats[1] += 1
            if person.is_alias:
                person = person.is_alias_of
                if person.ftm_eid:
                    print("After redirecting to alias, found an existing value.")
                    continue

            if person.ftm_eid:
                print("Found an existing value. Could be from the alias?")
                continue

            person.ftm_eid = judge_matches[0]['eid']
            person.ftm_total_received = judge_matches[0]['total']
            if not debug:
                person.save()
        elif len(judge_matches) == 0:
            match_stats[0] += 1
            print("  Found no matches.")
        elif len(judge_matches) > 1:
            match_stats[len(judge_matches)] += 1
            print("  Found multiple matches: %s" % judge_matches)

    print_stats(match_stats, candidate_id_map)


def update_judges_by_solr(candidate_id_map, debug):
    """An alternate attempt at updating judges, by looking each one up in
    Solr.
    """
    conn = SolrInterface(settings.SOLR_PEOPLE_URL, mode='r')
    match_stats = defaultdict(int)
    # These IDs are ones that cannot be updated due to being identified as
    # problematic in FTM's data.
    blacklisted_ids = defaultdict(list)
    for court_id, candidate_list in candidate_id_map.items():
        for candidate in candidate_list:
            # Look up the candidate in Solr.
            print("\nDoing: %s" % candidate['name'])
            name = (' AND '.join([word for word in candidate['name'].split() if
                                 len(word) > 1])).replace(',', '')
            results = conn.raw_query(**{
                'caller': 'ftm_update_judges_by_solr',
                'fq': [
                    'name:(%s)' % name,
                    'court_exact:%s' % court_id,
                    # This filters out Sr/Jr problems by insisting on recent
                    # positions. 1980 is arbitrary, based on testing.
                    'date_start:[1980-12-31T23:59:59Z TO *]',
                ],
                'q': "*:*",
            }).execute()

            if len(results) == 0:
                match_stats[len(results)] += 1
                print("  Found no matches.")

            elif len(results) == 1:
                match_stats[len(results)] += 1
                print("  Found one match: %s" % results[0]['name'])

                # Get the person from the DB and update them.
                pk = results[0]['id']
                if pk in blacklisted_ids:
                    continue
                p = Person.objects.get(pk=pk)
                if p.ftm_eid:
                    print("  Found values in ftm database fields. This "
                          "indicates a duplicate in FTM.")
                    p.ftm_eid = ""
                    p.ftm_total_received = None
                    if not debug:
                        p.save()
                    blacklisted_ids[p.pk].append(candidate)
                else:
                    # No major problems. Proceed.
                    p.ftm_eid = candidate['eid']
                    p.ftm_total_received = candidate['total']
                    if not debug:
                        p.save()

            elif len(results) > 1:
                match_stats[len(results)] += 1
                print("  Found more than one match: %s" % results)

    print_stats(match_stats, candidate_id_map)


class Command(BaseCommand):
    help = ("Use the Follow the Money API to lookup judges by name and "
            "jurisdiction. Once looked up, save the ID to the DB.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            default=False,
            help="Don't change the data.",
        )
        parser.add_argument(
            '--dont-use-pickle',
            action='store_false',
            default=True,
            help="Don't use a pickle file if one exists.",
        )

    def handle(self, *args, **options):
        self.debug = options['debug']
        self.options = options

        # Run the requested method.
        candidate_id_map = make_dict_of_ftm_eids(options['dont_use_pickle'])
        #update_judges(candidate_id_map, debug=options['debug'])

        update_judges_by_solr(candidate_id_map, debug=options['debug'])
