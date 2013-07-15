from datetime import date

# Reporters currently covered in the CourtListener database
# Note that these are used in the tokenizer as part of a regular expression. That regex matches tokens in the order of
# this list. As a result, it's vital that later editions of reporters come before earlier ones.
CL_REPORTERS = [
    # Supreme Court
    'U.S.',
    'S. Ct.',
    'L. Ed. 2d',
    'L. Ed.',
    'Dall.',
    'Cranch',
    'Wheat.',
    'Pet.',
    'How.',
    'Black',
    'Wall.',

    # Federal appellate
    'F.3d',
    'F.2d',
    'F. Supp. 2d',
    'F. Supp.',
    'F.',
    'Fed. Cl.',         # Court of Federal Claims
    'Ct. Cl.',          # Court of Federal Claims
    'B.R.',             # Bankruptcy Reporter
    'T.C.',             # Tax Court
    'M.J.',             # Military Justice
    'Vet. App.',        # Veterans Appeals
    "Ct. Int'l Trade",  # Court of International Trade

    # State regional reporters
    'N.E.2d',
    'N.E.',
    'A.3d',
    'A.2d',
    'A.',
    'S.E.2d',
    'S.E.',
    'So. 3d',
    'So. 2d',
    'So.',
    'S.W.3d',
    'S.W.2d',
    'S.W.',
    'N.W.2d',
    'N.W.',
    'P.3d',
    'P.2d',
    'P.',

    # Special State reporters.
    # Note that these must be listed before the N.Y. reporter so that N.Y.3d has the edge over N.Y.
    'Cal. Rptr. 3d',
    'Cal. Rptr. 2d',
    'Cal. Rptr.',
    'Cal. App. 4th',
    'Cal. App. 3d',
    'Cal. App. 2d',
    'Cal. App. Supp. 3d',
    'Cal. App. Supp. 2d',
    'Cal. App. Supp.',
    'Cal. App.',
    'N.Y.3d',  # New York Reports
    'N.Y.2d',
    'N.Y.',
    'N.Y.S.3d',  # New York Supplement Reports
    'N.Y.S.2d',
    'N.Y.S.',
    'A.D.3d',  # NY Appellate Division Reports
    'A.D.2d',
    'A.D.',
    'Misc. 3d',  # NY Miscellaneous Reports
    'Misc. 2d',
    'Misc.',
    'NY Slip Op',
    'Ohio St. 3d',

    # Advance citations
    'Nev. Adv. Op. No.',

    # State reporters
    'Ala.',
    'Alaska',
    'Ariz. App.',
    'Ariz.',
    'Ark.',
    'Cal. 4th',
    'Cal. 3d',
    'Cal. 2d',
    'Cal.',
    'Colo.',
    'Conn. App.',
    'Conn.',
    'D.C.',
    'Del.',
    'Fla.',
    'Ga. App.',
    'Ga.',
    'Haw.',
    'Idaho',
    'Ill. Dec.',
    'Ill. App. 3d',
    'Ill. App. 2d',
    'Ill. App.',
    'Ill.',
    'Ind.',
    'Iowa',
    'Kan. App. 2d',
    'Kan. App.',
    'Kan.',
    'Ky.',
    'La.',
    'Mass. App. Ct.',
    'Mass.',
    'Md. App.',
    'Md.',
    'Me.',
    'Mich. App.',
    'Mich.',
    'Minn.',
    'Miss.',
    'Mo.',
    'Mont.',
    'N.C. App.',
    'N.C.',
    'N.D.',
    'N.H.',
    'N.J. Tax',
    'N.J. Super.',
    'N.J.',
    'N.M.',
    'N.Y.',
    'Neb. App.',
    'Neb.',
    'Nev.',
    'Ohio',
    'Okla.',
    'Or.',
    'Pa. Commw.',
    'Pa. Super.',
    'Pa.',
    'P.R.',
    'R.I.',
    'S.C.',
    'S.D.',
    'Tenn.',
    'Tex.',
    'Utah',
    'Va. App.',
    'Va.',
    'Vt.',
    'W.Va.',
    'Wash. Terr.',  # Washington Territory Reports
    'Wash. App.',
    'Wash. 2d',
    'Wash.',
    'Wis. 2d',
    'Wis.',
    'Wyo.',
]

NEUTRAL_CITATIONS = [
    # Neutral citations
    'AZ',
    'CO',
    'FL',
    'LA',
    'ME',
    'MS',
    'MT',
    'ND App',
    'ND',
    'NMCA',
    'NMCERT',
    'NMSC',  # New Mexico Supreme Court
    'NM',
    'OH',
    'OK CR',
    'OK CIV APP',
    'OK',
    'SD',
    'PA',
    'UT App',
    'UT',
    'VT',
    'WI App',
    'WI',
    'WY',
]

# List of Federal Reporters
CL_REPORTERS.extend(NEUTRAL_CITATIONS)
REPORTERS = CL_REPORTERS

# We normalize spaces and other errors people make
# See note on REPORTERS for ordering of this list.
VARIATIONS = {
    # Supreme Court
    'U. S.': 'U.S.',
    'S.Ct': 'S. Ct.',
    'L.Ed.2d': 'L. Ed. 2d',
    'L.Ed. 2d': 'L. Ed. 2d',
    'L. Ed.2d': 'L. Ed. 2d',
    'L.Ed.': 'L. Ed.',

    # Federal appellate
    'F. 3d': 'F.3d',
    'F. 2d': 'F.2d',
    'F.Supp.2d': 'F. Supp. 2d',
    'F.Supp. 2d': 'F. Supp. 2d',
    'F. Supp.2d': 'F. Supp. 2d',
    'F.Supp.': 'F. Supp.',
    'Fed.Cl.': 'Fed. Cl.',
    'Ct.Cl.': 'Ct. Cl.',
    'B. R.': 'B.R.',
    'BR': 'B.R.',
    'T. C.': 'T.C.',
    'M. J.': 'M.J.',
    'Vet.App.': 'Vet. App.',
    "Ct.Int'l Trade": "Ct. Int'l Trade",

    # State regional reporters
    'N. E. 2d': 'N.E.2d',
    'N.E. 2d': 'N.E.2d',
    'N. E.2d': 'N.E.2d',
    'NE 2d': 'N.E.2d',
    'N. E.': 'N.E.',
    'A. 2d': 'A.2d',
    'A. 3d': 'A.3d',
    'S.E. 2d': 'S.E.2d',
    'S. E. 2d': 'S.E.2d',
    'S. E.2d': 'S.E.2d',
    'SE 2d': 'S.E.2d',
    'S. E.': 'S.E.',
    'So.2d': 'So. 2d',
    'So.3d': 'So. 3d',
    'S. W. 2d': 'S.W.2d',
    'S.W. 2d': 'S.W.2d',
    'S. W.2d': 'S.W.2d',
    'S. W. 3d': 'S.W.3d',
    'S.W. 3d': 'S.W.3d',
    'S. W.3d': 'S.W.3d',
    'SW 3d': 'S.W.3d',
    'S. W.': 'S.W.',
    'N. W. 2d': 'N.W.2d',
    'N.W. 2d': 'N.W.2d',
    'N. W.2d': 'N.W.2d',
    'NW 2d': 'N.W.2d',
    'N. W.': 'N.W.',
    'P. 2d': 'P.2d',
    'P. 3d': 'P.3d',

    # State special reporters
    'Cal.Rptr.3d': 'Cal. Rptr. 3d',
    'Cal.Rptr. 3d': 'Cal. Rptr. 3d',
    'Cal. Rptr.3d': 'Cal. Rptr. 3d',
    'Cal.Rptr.2d': 'Cal. Rptr. 2d',
    'Cal.Rptr. 2d': 'Cal. Rptr. 2d',
    'Cal. Rptr.2d': 'Cal. Rptr. 2d',
    'Cal.Rptr.': 'Cal. Rptr.',
    'Cal.4th': 'Cal. 4th',
    'Cal.3d': 'Cal. 3d',
    'Cal.2d': 'Cal. 2d',
    'Cal.App.4th': 'Cal. App. 4th',
    'Cal. App.4th': 'Cal. App. 4th',
    'Cal.App. 4th': 'Cal. App. 4th',
    'Cal.App.3d': 'Cal. App. 3d',
    'Cal. App.3d': 'Cal. App. 3d',
    'Cal.App. 3d': 'Cal. App. 3d',
    'Cal.App.2d': 'Cal. App. 2d',
    'Cal. App.2d': 'Cal. App. 2d',
    'Cal.App. 2d': 'Cal. App. 2d',
    'Cal.App.': 'Cal. App.',
    'Cal.App.3d Supp.': 'Cal. App. Supp. 3d',  # People get the order of these wrong.
    'Cal.App. 3d Supp.': 'Cal. App. Supp. 3d',
    'Cal.App.2d Supp.': 'Cal. App. Supp. 2d',
    'Cal.App. 2d Supp.': 'Cal. App. Supp. 2d',
    'Cal.App. Supp. 3d': 'Cal. App. Supp. 3d',  # These are the correct order (wrong spacing).
    'Cal.App. Supp.3d': 'Cal. App. Supp. 3d',
    'Cal.App. Supp. 2d': 'Cal. App. Supp. 2d',
    'Cal.App. Supp.2d': 'Cal. App. Supp. 2d',
    'Cal.App.Supp.': 'Cal. App. Supp.',
    'Ill.Dec.': 'Ill. Dec.',
    'Ill. App.3d': 'Ill. App. 3d',
    'Ill. App.2d': 'Ill. App. 2d',
    'Kan.App.2d': 'Kan. App. 2d',
    'Kan.App. 2d': 'Kan. App. 2d',
    'Kan. App.2d': 'Kan. App. 2d',
    'Kan.App.': 'Kan. App.',
    'N.Y. 3d': 'N.Y.3d',
    'NY 3d': 'N.Y.3d',
    'N.Y. 2d': 'N.Y.2d',
    'NY 2d': 'N.Y.2d',
    'N. Y.': 'N.Y.',
    'N.Y.S. 3d': 'N.Y.S.3d',
    'NYS 3d': 'N.Y.S.3d',
    'N.Y.S. 2d': 'N.Y.S.2d',
    'NYS 2d': 'N.Y.S.2d',
    'A.D. 3d': 'A.D.3d',
    'AD 3d': 'A.D.3d',
    'A.D. 2d': 'A.D.2d',
    'AD 2d': 'A.D.2d',
    'Misc.3d': 'Misc. 3d',
    'Misc 3d': 'Misc. 3d',
    'Misc.2d': 'Misc. 2d',
    'Misc 2d': 'Misc. 2d',
    'Ohio St.3d': 'Ohio St. 3d',
    'Wn.2d': 'Wn. 2d',
    'Wn.App.': 'Wn. App.',

    # State citations
    'Pa. Commonwealth Ct.': 'Pa. Commw.',
    'Pa. Superior Ct.': 'Pa. Super.',
    'Puerto Rico': 'P.R.',
    'Wn. Terr.': 'Wash. Terr.',  # Normalize Washington reporters (local rules?)
    'Wn. App.': 'Wash. App.',
    'Wn. 2d': 'Wash. 2d',
    'Wn': 'Wash.',
    'Wis.2d': 'Wis. 2d',

    # State neutral citations
    '-Ohio-': 'Ohio',
}

REPORTER_DATES = {
    # Federal appeals
    'F.': (date(1880, 1, 1),
           date(1924, 12, 31)),
    'F.2d': (date(1924, 1, 1),
             date(1993, 12, 31)),
    'F.3d': (date(1993, 1, 1),
             date.today()),
    'F. Supp.': (date(1933, 1, 1),
                 date(1998, 12, 31)),
    'F. Supp. 2d': (date(1998, 1, 1),
                    date.today()),
    'L. Ed.': (date(1790, 1, 1),
               date(1956, 12, 31)),
    'L. Ed. 2d.': (date(1956, 1, 1),
                   date.today()),

    # State regional reporters
    'P.': (date(1883, 1, 1),
           date(1931, 12, 31)),
    'P.2d': (date(1931, 1, 1),
             date(2000, 12, 31)),
    'P.3d': (date(2000, 1, 1),
             date.today()),


    # State special
    'Cal. Rptr.': (date(1959, 1, 1),
                   date(1991, 12, 31)),
    'Cal. Rptr. 2d': (date(1991, 1, 1),
                      date(2003, 12, 31)),
    'Cal. Rptr. 3d': (date(2003, 1, 1),
                      date.today()),

    # State
    'Cal.': (date(1850, 1, 1),
             date(1934, 12, 31)),
    'Cal. 2d': (date(1934, 1, 1),
                date(1969, 12, 31)),
    'Cal. 3d': (date(1969, 1, 1),
                date(1991, 12, 31)),
    'Cal. 4th': (date(1991, 1, 1),
                 date.today()),
    'Cal. App.': (date(1905, 1, 1),
                  date(1934, 12, 31)),
    'Cal. App. 2d': (date(1934, 1, 1),
                     date(1969, 12, 31)),
    'Cal. App. 3d': (date(1969, 1, 1),
                     date(1991, 12, 31)),
    'Cal. App. 4th': (date(1991, 1, 1),
                      date.today()),
}
