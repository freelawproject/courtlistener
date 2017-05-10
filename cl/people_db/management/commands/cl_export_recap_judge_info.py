from __future__ import print_function
from collections import Counter, OrderedDict

import pandas
from django.core.management import BaseCommand
from django.db.models import Q

from juriscraper.lib.string_utils import titlecase
from pandas import to_pickle
from unidecode import unidecode

from cl.search.models import Court, Docket

titles = [
    'judge', 'magistrate', 'district', 'chief', 'senior',
    'bankruptcy', 'mag.', 'magistrate-judge', 'mag/judge', 'mag',
    'visiting', 'special', 'senior-judge', 'master', 'u.s.magistrate',
]
blacklist = [
    'a998', 'agb', 'am', 'ca', 'cet', 'ch.', 'cla', 'clerk', 'cp', 'cvb', 'db',
    'debt-magistrate', 'discovery', 'dj', 'docket', 'duty', 'duty', 'ec', 'eck',
    'general', 'grc', 'gs', 'hhl', 'hon', 'honorable', 'inactive', 'jne', 'jv',
    'kec', 'law', 'lc', 'llh', 'lq', 'maryland', 'mediator', 'merged', 'mj',
    'mmh', 'msh', 'mwd', 'no', 'none', 'prisoner', 'pslc', 'pro', 'pso', 'pt',
    'rmh', 'se', 'sf', 'successor', 'u.s.', 'tjc', 'unassigned', 'unassigned2',
    'unassigneddj', 'unknown', 'us', 'usdc', 'vjdistrict',
]

judge_normalizers = {
    # Generic Judge & Bankruptcy Judge we merge together for simplicity.
    '': 'jud',
    'Judge': 'jud',
    'Judge Judge': 'jud',
    'District Judge': 'jud',
    'Visiting Judge': 'jud',
    'Bankruptcy': 'jud',
    'Bankruptcy Judge': 'jud',

    # Chief (normalize to jud for now, due to low sample size)
    'Chief': 'jud',
    'Chief Judge': 'jud',
    'Chief District Judge': 'jud',

    # Magistrate
    'Mag': 'mag',
    'Mag Judge': 'mag',
    'mag/judge': 'mag',
    'Magistrate': 'mag',
    'Magistrate Judge': 'mag',
    'Magistrate-Judge': 'mag',
    'Magistrate Judge Mag': 'mag',
    'Magistrate Judge Magistrate': 'mag',
    'Magistrate Judge Magistrate Judge': 'mag',

    # Chief Magistrate (normalize to magistrate for now, due to low sample size)
    'Chief Magistrate': 'mag',
    'Chief Magistrate Judge': 'mag',

    # Senior
    'Senior Judge': 'ret-senior-jud',
    'Senior-Judge': 'ret-senior-jud',

    # Special Master
    'Special Master': 'spec-m',
    'Chief Special Master': 'c-spec-m',
}


def normalize_judge_titles(title):
    """Normalize judge titles

    Take in a string like "Magistrate Judge" and return the normalized
    abbreviation from the POSITION_TYPES variable. Assumes that input is
    titlecased.

    Also normalizes things like:
     - District Judge --> Judge
     - Blank --> Judge
     - Bankruptcy Judge --> Judge
    """
    return judge_normalizers.get(title, 'UNKNOWN: %s' % title)


def normalize_judge_names(name):
    """Cleans up little issues with people's names"""
    out = []
    words = name.split()
    for i, w in enumerate(words):
        # Michael J Lissner --> Michael J. Lissner
        if len(w) == 1 and w.isalpha():
            w = '%s.' % w

        # Michael Lissner Jr --> Michael Lissner Jr.
        if w.lower() in ['jr', 'sr']:
            w = '%s.' % w

        # J. Michael Lissner --> Michael Lissner
        # J. G. Lissner --> J. G. Lissner
        if i == 0 and w.lower() in ['j.', 'j']:
            next_word = words[i + 1]
            if not any([len(next_word) == 2 and next_word.endswith('.'),
                        len(next_word) == 1]):
                # Drop the word.
                continue
        out.append(w)

    return ' '.join(out)


def split_name_title(judge):
    """Split a value from PACER and return the title and name"""
    judge = judge.replace(',', '')
    words = judge.lower().split()

    # Nuke bad junk (punct., j, blacklist, etc.)
    clean_words = []
    for i, w in enumerate(words):
        if any(['(' in w,
                ')' in w,
                w.startswith('-'),
                w.startswith('~'),
                (len(w) > 2 and '.' in w and w not in ['jr.', 'sr.']),
                w in blacklist]):
            continue
        clean_words.append(w)

    title_words = []
    name_words = []
    for w in clean_words:
        if w in titles:
            title_words.append(w)
        else:
            name_words.append(w)

    title = normalize_judge_titles(titlecase(' '.join(title_words)))
    name = normalize_judge_names(titlecase(' '.join(name_words)))

    return name, title


class Command(BaseCommand):
    help = 'Export a CSV of RECAP judges.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            default=False,
            help="Don't change the data."
        )

    def handle(self, *args, **options):
        self.debug = options['debug']
        self.options = options
        self.generate_data()

    def generate_data(self):
        """Make a CSV of the data extracted from the database.

        CSV will have the following format:
            Court, Name, Title, Count, 2000, 2011...

        {
            'ca2': {
                "harold baller": {
                    "Mag judge": {
                        "years": {
                            "1999': 22,
                            "2000': 14,
                        },
                        'total count': 36,
                    },
                }
            }
        }
        """
        courts = Court.objects.filter(jurisdiction__in=['FB', 'FD', 'F', 'FBP',
                                                        'FS'])
        out = {}
        for court in courts:
            out[court.pk] = {}
            dockets = (court.dockets
                       .exclude(Q(assigned_to_str='') & Q(referred_to_str=''))
                       .filter(source__in=Docket.RECAP_SOURCES)
                       .only('assigned_to_str', 'referred_to_str',
                             'date_filed'))
            print("Processing %s dockets in %s" % (dockets.count(), court.pk))
            for docket in dockets:
                for judge_type in ['assigned', 'referred']:
                    judge = getattr(docket, '%s_to_str' % judge_type)
                    if not judge:
                        continue

                    name, title = split_name_title(unidecode(judge))
                    if not name:
                        continue
                    if name not in out[court.pk]:
                        # No entry for this person.
                        out[court.pk][name] = {
                            title: Counter([docket.date_filed.year]),
                        }
                    else:
                        # Person already exists.
                        if title not in out[court.pk][name]:
                            # Title not yet found.
                            out[court.pk][name][title] = Counter(
                                [docket.date_filed.year])
                        else:
                            # Title already exists.
                            out[court.pk][name][title][
                                docket.date_filed.year] += 1

        self.export_files(out)

    @staticmethod
    def export_files(out):
        to_pickle(out, 'recap_export.pkl')
        out_csv = []
        for court, v in out.items():
            for judge_name, data in v.items():
                for title, years in data.items():
                    row = OrderedDict([
                        ('court', court),
                        ('name', judge_name),
                        ('title', title),
                        ('total count', sum(years.values()))
                    ])
                    for year, count in years.items():
                        row[str(year)] = count
                    out_csv.append(row)
        df = pandas.DataFrame(out_csv)
        df = df[['court', 'name', 'title', 'total count'] + sorted(
            [x for x in df.columns if x.isdigit()])]
        df.to_csv('recap_export.csv', index=False)
