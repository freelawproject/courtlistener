from datetime import date

# Reporters currently covered in the CourtListener database
CL_REPORTERS = [
    # Supreme Court
    'U.S.',
    'S. Ct.',
    'L. Ed.',
    'L. Ed. 2d',
    'Dall.',
    'Cranch',
    'Wheat.',
    'Pet.',
    'How.',
    'Black',
    'Wall.',

    # Federal appellate
    'F.',
    'F.2d',
    'F.3d',
    'F. Supp.',
    'F. Supp. 2d',
    'Fed. Cl.',         # Court of Federal Claims
    'Ct. Cl.',          # Court of Federal Claims
    'B.R.',             # Bankruptcy Reporter
    'T.C.',             # Tax Court
    'M.J.',             # Military Service Court of Criminal Appeals
    'Vet. App.',        # Veterans Appeals
    "Ct. Int'l Trade",  # Court of International Trade

    # State regional reporters
    'N.E.',
    'A.',
    'A.2d',
    'A.3d',
    'S.E.',
    'S.E.2d',
    'So.',
    'So. 2d',
    'So. 3d',
    'S.W.',
    'S.W.2d',
    'S.W.3d',
    'N.W.',
    'N.W.2d',
    'P.',
    'P.2d',
    'P.3d',
    'N.Y.S.',
    'N.Y.S.2d',
    'N.Y.S.3d',

    # State reporters
    'Ala.',
    'Alaska',
    'Ariz.',
    'Ark.',
    'Cal.',
    'Colo.',
    'Conn.',
    'D.C.',
    'Del.',
    'Fla.',
    'Ga.',
    'Haw.',
    'Idaho',
    'Ill.',
    'Ind.',
    'Iowa',
    'Kan.',
    'Ky.',
    'La.',
    'Mass.',
    'Md.',
    'Me.',
    'Mich.',
    'Minn.',
    'Miss.',
    'Mo.',
    'Mont.',
    'N.C.',
    'N.D.',
    'N.H.',
    'N.J.',
    'N.M.',
    'N.Y.',
    'Neb.',
    'Nev.',
    'Ohio',
    'Okla.',
    'Or.',
    'Pa.',
    'Puerto Rico',
    'R.I.',
    'S.C.',
    'S.D.',
    'Tenn.',
    'Tex.',
    'Utah',
    'Va.',
    'Vt.',
    'W.Va.',
    'Wash.',
    'Wis.',
    'Wyo.',
]

# List of Federal Reporters
REPORTERS = [
    "U.S.",
    "S. Ct.",
    "L. Ed.",
    "L. Ed. 2d",
    "F.",
    "F.2d",
    "F.3d",
    "F. Supp.",
    "F. Supp. 2d",
    "F.R.D.",
    "B.R.",
    "Vet. App.",
    "M.J.",
    "Fed. Cl.",
    "Ct. Int'l Trade",
    "T.C."
]

# We normalize spaces and other errors people make
VARIATIONS = {
    # Supreme Court
    'U. S.': 'U.S.',
    'S.Ct': 'S. Ct.',
    'L.Ed.': 'L. Ed.',
    'L.Ed.2d': 'L. Ed. 2d',
    'L.Ed. 2d': 'L. Ed. 2d',
    'L. Ed.2d': 'L. Ed. 2d',

    # Federal appellate
    'F. 2d': 'F.2d',
    'F. 3d': 'F.3d',
    'F.Supp.': 'F. Supp.',
    'F.Supp.2d': 'F. Supp. 2d',
    'F.Supp. 2d': 'F. Supp. 2d',
    'F. Supp.2d': 'F. Supp. 2d',
    'Fed.Cl.': 'Fed. Cl.',
    'Ct.Cl.': 'Ct. Cl.',
    'B. R.': 'B.R.',
    'T. C.': 'T.C.',
    'M. J.': 'M.J.',
    'Vet.App.': 'Vet. App.',
    "Ct.Int'l Trade": "Ct. Int'l Trade",

    # State regional reporters
    'N. E.': 'N.E.',
    'A. 2d': 'A.2d',
    'A. 3d': 'A.3d',
    'S. E.': 'S.E.',
    'S.E. 2d': 'S.E.2d',
    'S. E. 2d': 'S.E.2d',
    'S. E.2d': 'S.E.2d',
    'So.2d': 'So. 2d',
    'So.3d': 'So. 3d',
    'S. W.': 'S.W.',
    'S. W. 2d': 'S.W.2d',
    'S.W. 2d': 'S.W.2d',
    'S. W.2d': 'S.W.2d',
    'S. W. 3d': 'S.W.3d',
    'S.W. 3d': 'S.W.3d',
    'S. W.3d': 'S.W.3d',
    'N. W.': 'N.W.',
    'N. W. 2d': 'N.W.2d',
    'N.W. 2d': 'N.W.2d',
    'N. W.2d': 'N.W.2d',
    'P. 2d': 'P.2d',
    'P. 3d': 'P.3d',
    'N.Y.S. 2d': 'N.Y.S.2d',
    'N.Y.S. 3d': 'N.Y.S.3d',
}

REPORTER_DATES = {
    'F.': (1880, 1924),
    'F.2d': (1924, 1993),
    'F.3d': (1999, date.today().year),
    'F. Supp.': (1933, 1998),
    'F. Supp. 2d': (1998, date.today().year),
    'L. Ed.': (1790, 1956),
    'L. Ed. 2d.': (1956, date.today().year)
}
