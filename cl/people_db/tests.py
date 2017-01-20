from unittest import TestCase

from cl.people_db.management.commands.cl_export_recap_judge_info import \
    split_name_title, normalize_judge_names


class RECAPExportTest(TestCase):
    def test_title_name_splitter(self):
        pairs = [{
                'q': 'Magistrate Judge George T. Swartz',
                'a': ('George T. Swartz', 'mag'),
            },
            {
                'q': 'J. Frederick Motz',
                'a': ('Frederick Motz', 'jud'),
            },
            {
                'q': 'Honorable Susan W. Wright',
                'a': ('Susan W. Wright', 'jud'),
            },
        ]

        for pair in pairs:
            self.assertEqual(pair['a'], split_name_title(pair['q']))

    def test_name_normalization(self):
        pairs = [{
            'q': 'Michael J Lissner',
            'a': 'Michael J. Lissner',
        }, {
            'q': 'Michael Lissner Jr',
            'a': 'Michael Lissner Jr.',
        }, {
            'q': 'J Michael Lissner',
            'a': 'Michael Lissner',
        }, {
            'q': 'J. Michael J Lissner Jr',
            'a': 'Michael J. Lissner Jr.',
        }, {
            'q': 'J. J. Lissner',
            'a': 'J. J. Lissner',
        }]
        for pair in pairs:
            self.assertEqual(pair['a'], normalize_judge_names(pair['q']))
