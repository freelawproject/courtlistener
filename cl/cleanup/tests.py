# coding=utf-8
from django.test import TestCase
from cl.cleanup.management.commands.fix_tax_court import get_tax_docket_numbers


class CleanupTest(TestCase):

    def test_tax_court_cleanup_docket_numbers(self):
        """Can we find and make Citation objects from strings?"""
        test_pairs = (
            # Basic test
            ("""            
                        T.C. Memo. 2013-100




                        UNITED STATES TAX COURT




         LORRAINE C. BOYD AND MARVIN T. BOYD, Petitioners v.
          COMMISSIONER OF INTERNAL REVENUE, Respondent




      Docket No. 1780-12L.                         Filed April 11, 2013.




      Lorraine C. Boyd and Marvin T. Boyd, pro sese.

      Sze Wan Florence Char, for respondent.




                          MEMORANDUM OPINION


      WELLS, Judge: This case is before the Court on respondent’s motion to

dismiss for lack of jurisdiction, respondent’s motion for summary judgment
                                          -2-""",
             "1780-12L"),


            ("""
                        T.C. Memo. 2018-28



                  UNITED STATES TAX COURT



     DAVID KEEFE AND CANDACE KEEFE, Petitioners v.
    COMMISSIONER OF INTERNAL REVENUE, Respondent



Docket Nos. 15189-14, 29804-15.              Filed March 15, 2018.
            29804-16.



Richard Michael Gabor, for petitioners.

Eliezer Klein and Peter N. Scharff, for respondent.
                                        -2-

[*2]         MEMORANDUM FINDINGS OF FACT AND OPINION


       MARVEL, Chief Judge: Respondent determined the following deficiencies

in Federal income tax, accuracy-related penalties under section 6662(a),1 and

additions to tax under section 6651(a)(1) with respect to petitioners’ joint Federal

income tax returns:

                                              Penalty          Addition to tax
           Year          Deficiency         sec. 6662(a)       sec. 6651(a)(1)
           2004            $78,292            $15,658                 --
           2005            144,053             28,811                 --
           2006            218,228             43,646               $408
           2007            143,729             28,161                675
           2008            141,870             12,817             35,468
           2009            252,777             50,555                 --
           2010            309,060             61,812                 --""",
             "15189-14, 29804-15, 29804-16"),
        )


        for q, a in test_pairs:
            print "Testing docket number extraction for %s..." % a,
            docket_numbers_found = get_tax_docket_numbers(q)
            print docket_numbers_found
            self.assertEqual(
                docket_numbers_found,
                a,
                msg="Success"
            )
            print "✓"

    def test_tax_court_citation_extractor(self):
        """Find Tax Court Citations """

        test_pairs = (
            ("""  1 UNITED STATES TAX COURT REPORT (2018)    



                     UNITED STATES TAX COURT




 BENTLEY COURT II LIMITED PARTNERSHIP, B.F. BENTLEY, INC., TAX
                 MATTERS PARTNER, Petitioner v.
          COMMISSIONER OF INTERNAL REVENUE, Respondent



     Docket No. 5393-04.                Filed May 31, 2006.



     Nancy Ortmeyer Kuhn, for petitioner.
        """, {'reporter_index': 1,
              'canonical_reporter': u'T.C.',
              'match_id': None,
              'extra': None,
              'plaintiff': None,
              'reporter': u'T.C.',
              'year': None,
              'volume': 1,
              'reporter_found': 'UNITED STATES TAX COURT REPORT',
              'cite_type': 4, 'lookup_index': 0,
              'court': None,
              'equality_attributes': ['reporter', 'volume', 'page',
                                      'canonical_reporter', 'lookup_index'],
              'match_url': None,
              'page': 2018,
              'defendant': None}),

                ("""  T.C. Memo. 2003-150



                                  UNITED STATES TAX COURT



                       RIVER CITY RANCHES #1 LTD., LEON SHEPARD,
                                  TAX MATTERS PARTNER,
                       RIVER CITY RANCHES #2 LTD., LEON SHEPARD,
                                   TAX MATTERS PARTNER,
                        RIVER CITY RANCHES #3 LTD., LEON SHEPARD,
                                   TAX MATTERS PARTNER,


                """, {'reporter_index': 0,
                      'canonical_reporter': u'T.C. Memo.',
                      'match_id': None,
                      'extra': None,
                      'plaintiff': None,
                      'reporter': 'T.C. Memo.',
                      'year': None,
                      'volume': 2003,
                      'reporter_found': 'T.C. Memo.',
                      'cite_type': 8,
                      'lookup_index': 0,
                      'court': None,
                      'equality_attributes': ['reporter', 'volume', 'page',
                                              'canonical_reporter',
                                              'lookup_index'],
                      'match_url': None,
                      'page': 150,
                      'defendant': None}
)
        )
        for q, a in test_pairs:
            cite = generate_citation(q, 111)
            print cite
            print "Searching for %s" % a
            self.assertEqual(
                cite,
                a,
                msg="Success"
            )
            print "✓"
