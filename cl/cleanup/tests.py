# -*- coding: utf-8 -*-
import os
import re
import mock
from glob import iglob
import json

from django.test import TestCase
from django.conf import settings

from cl.cleanup.management.commands.fix_tax_court import (
    find_tax_court_citation,
    get_tax_docket_numbers,
)


class CitationTaxCleanup(TestCase):
    test_dir = os.path.join(
        settings.INSTALL_ROOT, "cl", "cleanup", "test_assets"
    )

    @mock.patch(
        "cl.cleanup.management.commands.fix_tax_court.find_tax_court_citation",
        side_effect=[iglob(os.path.join(test_dir, "working*"))],
    )
    def test_working_examples(self, mock):
        paths = mock()
        for path in paths:
            with open(path) as f:
                data = json.loads(f.read())
            cite = find_tax_court_citation(data["html"])
            self.assertEqual(cite.base_citation(), data["cite"])
            print("Success ✓")
            print(data["notes"])

    @mock.patch(
        "cl.cleanup.management.commands.fix_tax_court.find_tax_court_citation",
        side_effect=[iglob(os.path.join(test_dir, "failing*"))],
    )
    def test_failing_examples(self, mock):
        paths = mock()
        for path in paths:
            with open(path) as f:
                data = json.loads(f.read())
            cite = find_tax_court_citation(data["html"])
            self.assertFalse(cite)
            print ("Success ✓")

    @mock.patch(
        "cl.cleanup.management.commands.fix_tax_court.get_tax_docket_numbers",
        side_effect=[iglob(os.path.join(test_dir, "docket*"))],
    )
    def test_docket_parsing(self, mock):
        paths = mock()
        for path in paths:
            with open(path) as f:
                data = json.loads(f.read())
            for case in data:
                answer = re.sub("–", "-", case["answer"])
                answer = re.sub("—", "-", answer)
                answer = re.sub("–", "-", answer)
                print (answer)
                self.assertEqual(get_tax_docket_numbers(case["text"]), answer)
                print ("Success ✓")


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
            (
                """
                                                         MICHAEL KEITH SHENK, PETITIONER v. COMMISSIONER
                                                    OF INTERNAL REVENUE, RESPONDENT

                                                        Docket No. 5706–12.                            Filed May 6, 2013.

                                                  P was divorced from his wife, and their 2003 ‘‘Judgment of
                                               Absolute Divorce’’ provided that his ex-wife would have pri-
                                               mary residential custody of their three minor children. The
                                               judgment provided that the dependency exemption deductions
                                               for the three children would be divided between the two ex-
                                               spouses according to various conditions but did not provide
                                               that the ex-wife must execute in P’s favor a Form 8332,
                                               ‘‘Release of Claim to Exemption for Child of Divorced or Sepa-
                                               rated Parents’’. The children resided with P’s ex-wife for more
                                               than half of 2009, and P’s ex-wife did not execute in P’s favor
                                               any Form 8332 or equivalent document for any year. For 2009
                                               P timely filed a Federal income tax return on which he
                                               claimed dependency exemption deductions and the child tax
                                               credit for two of the children, consistent with his under-
                                               standing of the terms of the judgment, but he did not attach
                                               any Form 8332 to his return. He also claimed head-of-house-
                                               hold filing status. His ex-wife, the custodial parent, timely
                                               filed a Federal income tax return""",
                "5706–12",
            ),
        )
        for q, a in test_pairs:
            print("Searching for %s" % a, end=" ")
            docket_numbers_found = get_tax_docket_numbers(q)
            self.assertEqual(docket_numbers_found, a, msg="Success")
            print("✓")

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
                "1 T.C. 2018",
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
                "2003 T.C. Memo. 150",
            ),
            (
                """  T.C. Summary Opinion 2003-150



                                  UNITED STATES TAX COURT



                       RIVER CITY RANCHES #1 LTD., LEON SHEPARD,
                                  TAX MATTERS PARTNER,
                       RIVER CITY RANCHES #2 LTD., LEON SHEPARD,
                                   TAX MATTERS PARTNER,
                        RIVER CITY RANCHES #3 LTD., LEON SHEPARD,
                                   TAX MATTERS PARTNER,


                """,
                "2003 T.C. Summary Opinion 150",
            ),
            (
                """
                   MICHAEL KEITH SHENK, PETITIONER v. COMMISSIONER
                                                    OF INTERNAL REVENUE, RESPONDENT

                                                        Docket No. 5706–12.                            Filed May 6, 2013.

                                                  P was divorced from his wife, and their 2003 ‘‘Judgment of
                                               Absolute Divorce’’ provided that his ex-wife would have pri-
                                               mary residential custody of their three minor children. The
                                               judgment provided that the dependency exemption deductions
                                               for the three children would be divided between the two ex-
                                               spouses according to various conditions but did not provide
                                               that the ex-wife must execute in P’s favor a Form 8332,
                                               ‘‘Release of Claim to Exemption for Child of Divorced or Sepa-
                                               rated Parents’’. The children resided with P’s ex-wife for more
                                               than half of 2009, and P’s ex-wife did not execute in P’s favor
                                               any Form 8332 or equivalent document for any year. For 2009
                                               P timely filed a Federal income tax return on which he
                                               claimed dependency exemption deductions and the child tax
                                               credit for two of the children, consistent with his under-
                                               standing of the terms of the judgment, but he did not attach
                                               any Form 8332 to his return. He also claimed head-of-house-
                                               hold filing status. His ex-wife, the custodial parent, timely
                                               filed a Federal income tax return for 2009 on which she also

                                      200




VerDate Nov 24 2008   10:59 Jul 11, 2014   Jkt 372897    PO 20012   Frm 00001   Fmt 3857   Sfmt 3857   V:\FILES\BOUND VOL. WITHOUT CROP MARKS\B.V.140\SHENK   JAMIE
                                      (200)                          SHENK v. COMMISSIONER                                        201


                                               claimed two dependency exemption deductions, so that one
                                               child was claimed on both parents’ returns. R allowed to P the
                                               dependency exemption deduction for one of the children but
                                               disallowed his claim for the dependency exemption deduction
                                               for the child who had also been claimed by the custodial
                                               parent. At trial P contended he is entitled to a dependency
                                               exemption deduction for all three children. Held: Since the
                                               custodial parent did not execute, and P could not and did not
                                               attach to his return, any Form 8332 or equivalent release, P
                                               is not entitled under I.R.C. sec. 152(e)(2)(A) to claim the
                                               dependency exemption deduction or the child tax credit. Held,
                                               further, where both the custodial parent and the noncustodial
                                               parent have claimed for the same year a dependency exemp-
                                               tion deduction for the same child, a declaration signed by the
                                               custodial parent after the period of limitations for assess-
                                               ments has expired as to the custodial parent could not qualify
                                               under I.R.C. sec. 152(e)(2)(A), and therefore there is no reason
                                               to grant P’s request to leave the record open so that he may
                                               obtain and proffer such a declaration. Held, further, P is not
                                               entitled to head-of-household filing status under I.R.C. sec.
                                               2(b)(1) nor to the child tax credit under I.R.C. sec. 24.

                                           Michael Keith Shenk, for himself.
                                           Shari Salu, for respondent.
                                         GUSTAFSON, Judge: The Internal Revenue Service (IRS)
                                      determined a deficiency of $3,136 in the 2009 Federal income
                                      tax of petitioner Michael Keith Shenk. Mr. Shenk petitioned
                                      this Court, pursuant to section 6213(a), 1 for redetermination
                                      of the deficiency. After Mr. Shenk’s concession that he
                                      received but did not report $254 in dividend income, the
                                      issue for decision is whether Mr. Shenk is entitled to a
                                      dependency exemption deduction for one of his children
                                      under section 151(c), a child tax credit for that child under
                                      section 24(a), and head-of-household filing status under sec-
                                      tion 2(b)(1). On these issues, we hold for the IRS.
                                                                          FINDINGS OF FACT

                                      The judgment of divorce
                                        Mr. Shenk was married to Julie Phillips, and they have
                                      three minor children—M.S., W.S., and L.S. They divorced in
                                      2003. The family court’s ‘‘Judgment of Absolute Divorce’’ pro-
                                         1 Unless otherwise indicated, all citations of sections refer to the Internal

                                      Revenue Code (26 U.S.C.) in effect for the tax year at issue, and all cita-
                                      tions of Rules refer to the Tax Court Rules of Practice and Procedure.




VerDate Nov 24 2008   10:59 Jul 11, 2014   Jkt 372897   PO 20012   Frm 00002   Fmt 3857   Sfmt 3857   V:\FILES\BOUND VOL. WITHOUT CROP MARKS\B.V.140\SHENK   JAMIE
                                      202                 140 UNITED STATES TAX COURT REPORTS                                   (200)


                                      vided: that Ms. Phillips was ‘‘awarded primary residential
                                      custody’’ of the parties’ three children; and that Mr. Shenk
                                      would be liable for child support payments; but that, as to
                                      dependency exemptions—""",
                "140 T.C. 200",
            ),
        )
        for q, a in test_pairs:
            cite = find_tax_court_citation(q)
            cite_string = " ".join(
                [str(cite.volume), cite.reporter, str(cite.page)]
            )
            self.assertEqual(cite_string, a, msg="Success")
            print("✓")
