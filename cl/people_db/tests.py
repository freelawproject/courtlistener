from unittest import TestCase

from cl.people_db.management.commands.cl_export_recap_judge_info import \
    split_name_title


class RECAPExportTest(TestCase):
    def test_title_name_splitter(self):
        pairs = [{
                'q': 'Magistrate Judge George T. Swartz',
                'a': ('George T. Swartz', 'Magistrate Judge'),
            },
            {
                'q': 'J. Frederick Motz',
                'a': ('Frederick Motz', ''),
            },
            {
                'q': 'Honorable Susan W. Wright',
                'a': ('Susan W. Wright', ''),
            },
        ]

        for pair in pairs:
            self.assertEqual(split_name_title(pair['q']), pair['a'])
