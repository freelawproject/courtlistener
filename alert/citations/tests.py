from alert.citations.find_citations import get_citations, Citation
from alert.citations.reporter_tokenizer import tokenize
from django.test import TestCase


class CiteTest(TestCase):
    def test_reporter_tokenizer(self):
        """Do we tokenize correctly?"""
        self.assertEqual(tokenize('See Roe v. Wade, 410 U. S. 113 (1973)'),
                         ['See', 'Roe', 'v.', 'Wade,', '410', 'U. S.', '113', '(1973)'])
        self.assertEqual(tokenize('Foo bar eats grue, 232 Vet. App. (2003)'),
                         ['Foo', 'bar', 'eats', 'grue,', '232', 'Vet. App.', '(2003)'])

    def test_find_citations(self):
        """Can we find and make Citation objects from strings?"""
        test_pairs = [['1 U.S. 1',
                       Citation(volume=1, reporter='U.S.', page=1)],
                      ['lissner test 1 U.S. 1',
                       Citation(volume=1, reporter='U.S.', page=1)],
                      ['lissner v. test 1 U.S. 1',
                       Citation(plaintiff='lissner', defendant='test', volume=1, reporter='U.S.', page=1)],
                      ['lissner v. test 1 U.S. 1 (1982)',
                       Citation(plaintiff='lissner', defendant='test', volume=1, reporter='U.S.', page=1, year=1982)],
                      ['bob lissner v. test 1 F.2d 1 (1982)',
                       Citation(plaintiff='lissner', defendant='test', volume=1, reporter='F.2d', page=1, year=1982)],
                      ['bob lissner v. test 1 U.S. 1, 347-348 (4th Cir. 1982)',
                       Citation(plaintiff='lissner', defendant='test', volume=1, reporter='U.S.', page=1, year=1982,
                                extra='347-348', court='4th Cir')]]

        for pair in test_pairs:
            cite_found = get_citations(pair[0])[0]
            self.assertEqual(cite_found, pair[1],
                             msg='%s != \n                %s' % (cite_found.__dict__, pair[1].__dict__))
