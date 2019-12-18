# coding=utf-8
from django.test import TestCase
from cl.cleanup.management.commands.fix_tax_court import (
    generate_citation,
    get_tax_docket_numbers,
)


class CleanupTest(TestCase):
    def test_tax_court_cleanup_docket_numbers(self):
        """Find docket numbers in tax court opinions"""
        # First set of docket numbers is split over two pages- very difficult
        test_pairs = (
            (
                """  T.C. Memo. 2003-150



                      UNITED STATES TAX COURT



           RIVER CITY RANCHES #1 LTD., LEON SHEPARD,
                      TAX MATTERS PARTNER,
           RIVER CITY RANCHES #2 LTD., LEON SHEPARD,
                       TAX MATTERS PARTNER,
            RIVER CITY RANCHES #3 LTD., LEON SHEPARD,
                       TAX MATTERS PARTNER,
            RIVER CITY RANCHES #4 LTD., LEON SHEPARD,
                       TAX MATTERS PARTNER,
            RIVER CITY RANCHES #5 LTD., LEON SHEPARD,
                       TAX MATTERS PARTNER,
            RIVER CITY RANCHES #6 LTD., LEON SHEPARD,
                       TAX MATTERS PARTNER,
                     ET AL.,1 Petitioners v.
          COMMISSIONER OF INTERNAL REVENUE, Respondent



    Docket Nos.     787-91,    4876-94,   Filed May 23, 2003.
                   9550-94,    9552-94,
                   9554-94,   13595-94,
                  13597-94,   13599-94,
                    382-95,     383-95,

    1
        The Appendix sets forth, for each of these consolidated
cases, the docket number, partnership, and tax matters partner.
By orders issued from June 22, 2000, through May 15, 2001, the
Court removed Walter J. Hoyt III (Jay Hoyt), as tax matters
partner in each of the consolidated cases. In those orders, the
Court appointed a successor tax matters partner in each case.
                                 - 2 -

                     385-95,     386-95,
                   14718-95,   14719-95,
                   14720-95,   14722-95,
                   14724-95,   21461-95,
                    5196-96,    5197-96,
                    5198-96,    5238-96,
                    5239-96,    5240-96,
                    5241-96,    9779-96,
                    9780-96,    9781-96,
                   14038-96,   21774-96,
                    3304-97,    3305-97,
                    3306-97,    3311-97,
                    3749-97,   15747-98,
                   15748-98,   15749-98,
                   15750-98,   15751-98,
                   15752-98,   15753-98,
                   15754-98,   19106-98,
                   13250-99,   13251-99,
                   13256-99,   13257-99,
                   13258-99,   13259-99,
                   13260-99,   13261-99,
                   13262-99,   16557-99,
                   16563-99,   16568-99,
                   16570-99,   16572-99,
                   16574-99,   16578-99,
                   16581-99,   17125-99.


     Montgomery W. Cobb, for petitioners.

     Terri Ann Merriam and Wendy S. Pearson, for participating
partners in docket Nos. 9554-94, 13599-94, 383-95, and 16578-99.

     Thomas A. Dombrowski, Catherine A. Caballero, Alan E.
Staines, Thomas N. Tomashek, Dean H. Wakayama, and Nhi Luu, for
respondent.


                               Contents


FINDINGS OF FACT   . . . . . . . . . . . . . . . . . . . . . . . 7

A.   Overview of the Hoyt Operations       . . . . . . . . . . . . . 7

B.   Formation and Operation of the Hoyt Sheep Partnerships . . 9
                              - 3 -
            """,
                "787-91, 4876-94, 9550-94, 9552-94, 9554-94, 13595-94, 13597-94, 13599-94, 382-95, 383-95, 385-95, 386-95, 14718-95, 14719-95, 14720-95, 14722-95, 14724-95, 21461-95, 5196-96, 5197-96, 5198-96, 5238-96, 5239-96, 5240-96, 5241-96, 9779-96, 9780-96, 9781-96, 14038-96, 21774-96, 3304-97, 3305-97, 3306-97, 3311-97, 3749-97, 15747-98, 15748-98, 15749-98, 15750-98, 15751-98, 15752-98, 15753-98, 15754-98, 19106-98, 13250-99, 13251-99, 13256-99, 13257-99, 13258-99, 13259-99, 13260-99, 13261-99, 13262-99, 16557-99, 16563-99, 16568-99, 16570-99, 16572-99, 16574-99, 16578-99, 16581-99, 17125-99",
            ),
            (
                """            T.C. Memo. 2009-295



                     UNITED STATES TAX COURT



VIRGINIA HISTORIC TAX CREDIT FUND 2001 LP, VIRGINIA HISTORIC TAX
 CREDIT FUND 2001, LLC, TAX MATTERS PARTNER, ET AL.,1 Petitioner
         v. COMMISSIONER OF INTERNAL REVENUE, Respondent



     Docket Nos. 716-08, 870-08,       Filed December 21, 2009.
                 871-08.



          R issued a partnership and its two pass-thru
     partners (lower-tier partnerships) notices of final
     partnership administrative adjustment (FPAAs) for 2001
     and 2002 increasing each of the partnerships’ ordinary
     income for unreported sales of Virginia Historic
     Rehabilitation Tax Credits (State tax credits). In
     doing so, R determined that certain limited partners
     and members (investors) of the partnerships were not
     partners for Federal tax purposes but instead were
     purchasers of State tax credits from the partnerships.
     R determined, in the alternative, that the investors’


     1
      This case is consolidated for trial, briefing, and opinion
with Virginia Historic Tax Credit Fund""",
                "716-08, 870-08, 871-08",
            ),
            (
                """              T.C. Memo. 2010-266



                      UNITED STATES TAX COURT


          TAX PRACTICE MANAGEMENT, INC., Petitioner v.
          COMMISSIONER OF INTERNAL REVENUE, Respondent

     JOSEPH ANTHONY D’ERRICO, Petitioner v. COMMISSIONER OF
                   INTERNAL REVENUE, Respondent


     Docket Nos. 1477-09, 1483-09.    Filed December 7, 2010.



     Adam L. Karp, for petitioners.

     Jeremy L. McPherson, for respondent.


    """,
                "1477-09, 1483-09",
            ),
            (
                """                       T.C. Memo. 2006-113



                     UNITED STATES TAX COURT




 BENTLEY COURT II LIMITED PARTNERSHIP, B.F. BENTLEY, INC., TAX
                 MATTERS PARTNER, Petitioner v.
          COMMISSIONER OF INTERNAL REVENUE, Respondent



     Docket No. 5393-04L.                Filed May 31, 2006.



     Nancy Ortmeyer Kuhn, for petitioner.

     Wilton A. Baker, for respondent.""",
                "5393-04L",
            ),
        )
        for q, a in test_pairs:
            docket_numbers_found = get_tax_docket_numbers(q)
            print "Searching for %s" % a,
            self.assertEqual(docket_numbers_found, a, msg="Success")
            print "✓"

    def test_tax_court_citation_extractor(self):
        """Find Tax Court Citations """

        test_pairs = (
            (
                """  1 UNITED STATES TAX COURT REPORT (2018)    



                     UNITED STATES TAX COURT




 BENTLEY COURT II LIMITED PARTNERSHIP, B.F. BENTLEY, INC., TAX
                 MATTERS PARTNER, Petitioner v.
          COMMISSIONER OF INTERNAL REVENUE, Respondent



     Docket No. 5393-04.                Filed May 31, 2006.



     Nancy Ortmeyer Kuhn, for petitioner.
        """,
                {
                    "reporter_index": 1,
                    "canonical_reporter": u"T.C.",
                    "match_id": None,
                    "extra": None,
                    "plaintiff": None,
                    "reporter": u"T.C.",
                    "year": None,
                    "volume": 1,
                    "reporter_found": "UNITED STATES TAX COURT REPORT",
                    "cite_type": 4,
                    "lookup_index": 0,
                    "court": None,
                    "equality_attributes": [
                        "reporter",
                        "volume",
                        "page",
                        "canonical_reporter",
                        "lookup_index",
                    ],
                    "match_url": None,
                    "page": 2018,
                    "defendant": None,
                },
            ),
            (
                """  T.C. Memo. 2003-150



                                  UNITED STATES TAX COURT



                       RIVER CITY RANCHES #1 LTD., LEON SHEPARD,
                                  TAX MATTERS PARTNER,
                       RIVER CITY RANCHES #2 LTD., LEON SHEPARD,
                                   TAX MATTERS PARTNER,
                        RIVER CITY RANCHES #3 LTD., LEON SHEPARD,
                                   TAX MATTERS PARTNER,


                """,
                {
                    "reporter_index": 0,
                    "canonical_reporter": u"T.C. Memo.",
                    "match_id": None,
                    "extra": None,
                    "plaintiff": None,
                    "reporter": "T.C. Memo.",
                    "year": None,
                    "volume": 2003,
                    "reporter_found": "T.C. Memo.",
                    "cite_type": 8,
                    "lookup_index": 0,
                    "court": None,
                    "equality_attributes": [
                        "reporter",
                        "volume",
                        "page",
                        "canonical_reporter",
                        "lookup_index",
                    ],
                    "match_url": None,
                    "page": 150,
                    "defendant": None,
                },
            ),
        )
        for q, a in test_pairs:
            cite = generate_citation(q, 111)
            print cite
            print "Searching for %s" % a
            self.assertEqual(cite, a, msg="Success")
            print "✓"
