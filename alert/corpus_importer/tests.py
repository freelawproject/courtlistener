from django.test import TestCase
from alert.corpus_importer.import_law_box import get_docket_number
from alert.corpus_importer.judge_extractor import get_judge_from_str


class DocketNumberTest(TestCase):
    def test_extracting_docket_numbers(self):
        q_a_pairs = [
            ('Bankruptcy No. 87 B 15813, Adv. Nos. 87 A 1153, 87 A 1154',
             'Bankruptcy No. 87 B 15813, Adv. Nos. 87 A 1153, 87 A 1154'),
            ('88-2398.',
             '88-2398'),
            ('88 C 4430',
             '88 C 4430'),
            ('NO. 3328',
             'NO. 3328'),
            ('Record No. 32',
             'Record No. 32'),
        ]

        for q, a in q_a_pairs:
            self.assertEqual(get_docket_number(q), a)

class JudgeExtractionTest(TestCase):
    def test_extracting_judges_from_strings(self):
        pairs = (
            ('L. CHANDLER WATSON, Jr., Bankruptcy Judge.', u'L. Chandler Watson, Jr.', 2),
            ('VOLINN, Bankruptcy Judge:', u'Volinn', 1),
            ('McGOVERN, District Judge.', u'McGovern', 1),
            ('LEAPHART, Justice', u'Leaphart', 1),
        )

        for q, a, forward_test in pairs:
            self.assertEqual(get_judge_from_str(q, forward_test=forward_test), a)
