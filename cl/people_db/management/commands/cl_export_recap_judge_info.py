from collections import Counter, OrderedDict

import pandas
from django.core.management import BaseCommand
from django.db.models import Q

from juriscraper.lib.string_utils import titlecase
from pandas import to_pickle

from cl.search.models import Court, Docket

titles = [
    'judge', 'magistrate', 'district', 'chief', 'senior',
    'bankruptcy', 'mag.', 'magistrate-judge', 'mag/judge', 'mag',
    'visiting', 'special', 'senior-judge', 'master', 'u.s.magistrate',
]
blacklist = [
    '(settlement)',  'hon.', 'honorable', 'u.s.', 'unassigned', 'pro', 'se',
    'pslc',  'law', 'clerk', 'ch.', 'discovery', 'usdc', 'us',
]


def split_name_title(judge):
    """Split a value from PACER and return the title and name"""
    judge = judge.replace(',', '')
    words = judge.lower().split()

    # Nuke bad junk (punct., j, blacklist, etc.)
    clean_words = []
    for i, w in enumerate(words):
        if any(['(' in w,
                ')' in w,
                (len(w) > 2 and '.' in w),
                (i == 0 and w == 'j.'),
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

    title = titlecase(' '.join(title_words))
    name = titlecase(' '.join(name_words))

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
            Court, Name, Titles, Count, 2000, 2011...

        {
            'ca2': {
                "harold baller": {
                    "titles": {"Mag judge", "Senior Judge"},
                    "years": {
                        "1999': 22,
                        "2000': 14,
                    },
                    'total count': 36,
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
                       .only('assigned_to_str', 'referred_to_str', 'date_filed'))
            print "Processing %s dockets in %s" % (dockets.count(), court.pk)
            for docket in dockets:
                for judge_type in ['assigned', 'referred']:
                    judge = getattr(docket, '%s_to_str' % judge_type)
                    if not judge:
                        continue

                    name, title = split_name_title(judge)
                    if name not in out[court.pk]:
                        out[court.pk][name] = {
                            'titles': {title},
                            'years': Counter([docket.date_filed.year]),
                        }
                    else:
                        out[court.pk][name]['titles'].add(title)
                        out[court.pk][name]['years'][docket.date_filed.year] += 1
        self.export_files(out)

    @staticmethod
    def export_files(out):
        to_pickle(out, 'recap_export.pkl')
        out_csv = []
        for k, v in out.items():
            court = k
            for judge, data in v.items():
                titles = data['titles']
                years = data['years']
                titles_str = ';'.join(sorted(titles))
                row = OrderedDict([
                    ('court', court),
                    ('name', judge),
                    ('titles', titles_str),
                    ('total count', sum(years.values()))
                ])
                for year, count in years.items():
                    row[str(year)] = count
                out_csv.append(row)
        df = pandas.DataFrame(out_csv)
        df = df[['court', 'name', 'titles', 'total count'] + sorted(
            [x for x in df.columns if x.isdigit()])]
        df.to_csv('recap_export.csv', index=False)
