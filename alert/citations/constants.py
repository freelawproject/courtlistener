from datetime import date

# Reporters currently covered in the CourtListener database
# Note that these are used in the tokenizer as part of a regular expression. That regex matches tokens in the order of
# this list. As a result, it's vital that later editions of reporters come before earlier ones.

'''
example_var = {'U.S.': {'name': 'United States Reporter',
                        'variations': {'U. S.': 'U.S.'},
                        'editions': {'P.':   (date(1883, 1, 1), date(1931, 12, 31)),
                                     'P.2d': (date(1931, 1, 1), date(2000, 12, 31)),
                                     'P.3d': (date(2000, 1, 1), date.today())},
                        'mlz_jurisdiction': 'us'}
}
'''

'''
    Notes:
     - Most data was gathered from http://www.legalabbrevs.cardiff.ac.uk/
     - Formats follow the Blue Book standard.
     - The 'variations' key consists of data from local rules, or found through organic usage in our corpus. We have
       used a dict for these values due to the fact that there can be variations for each series.
     - mlz_jurisdiction corresponds to the work that is being done for reference software such as Zotero.
'''


REPORTERS = {
    #################
    # Supreme Court #
    #################
    'U.S.':
        {'name': 'United States Supreme Court Reports',
         'variations': {'U.S.S.C.Rep.': 'U.S.',
                        'USSCR':        'U.S.',},
         'editions': {'U.S.': (date(1790, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    'S. Ct.':
        {'name': 'West\'s Supreme Court Reporter',
         'variations': {'S Ct':         'S. Ct.',
                        'S.C.':         'S. Ct.',
                        'S.Ct.':        'S. Ct.',
                        'Sup.Ct.':      'S. Ct.',
                        'Sup.Ct.Rep.':  'S. Ct.',
                        'Supr.Ct.Rep.': 'S. Ct.',},
         'editions': {'S. Ct.': (date(1882, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    # What's bb for this one? Peter Martin says L. Ed., but Cardiff says L Ed
    'L. Ed.':
        {'name': 'Lawyer\'s Edition',
         'variations': {'L Ed': 'L. Ed.',
                        'L.E.': 'L. Ed.',
                        'L.Ed.': 'L. Ed.',
                        'L.Ed.(U.S.)': 'L. Ed.',
                        'LAW ED': 'L. Ed.',
                        'Law.Ed.': 'L. Ed.',
                        'U.S.L.Ed.': 'L. Ed.',
                        'U.S.Law.Ed.': 'L. Ed.',
                        'L Ed 2d': 'L. Ed. 2d',
                        'L.E.2d': 'L. Ed. 2d',
                        'L.Ed.2d': 'L. Ed. 2d',
                        'U.S.L.Ed.2d': 'L. Ed. 2d', },
         'editions': {'L. Ed.':    (date(1790, 1, 1), date(1956, 12, 31)),
                      'L. Ed. 2d': (date(1956, 1, 1), date.today()),},
         'mlz_jurisdiction': 'us'},
    'Dall.':
        {'name': 'Dallas\' Supreme Court Reports',
         'variations': {'Dal.': 'Dall.',
                        'Dall.S.C.': 'Dall.',
                        'Dallas': 'Dall.',
                        'U.S.(Dall.)': 'Dall.'},
         'editions': {'Dall': (date(1790, 1, 1), date(1880, 12, 31))},
         'mlz_jurisdiction': 'us'},
    'Cranch':
        {'name': 'Cranch\'s Supreme Court Reports',
         'variations': {'Cr.': 'Cranch',
                        'Cra.': 'Cranch',
                        'Cranch (US)': 'Cranch',
                        'U.S.(Cranch)': 'Cranch'},
         'editions': {'Cranch': (date(1801, 1, 1), date(1815, 12, 31))},
         'mlz_jurisdiction': 'us'},
    'Wheat.':
        {'name': 'Wheaton\'s Supreme Court Reports',
         'variations': {'U.S.(Wheat.)': 'Wheat.',
                        'Wheaton': 'Wheat.',},
         'editions': {'Wheat': (date(1816, 1, 1), date(1827, 12, 31))},
         'mlz_jurisdiction': 'us'},
    'Pet.':
        {'name': 'Peters\' Supreme Court Reports',
         'variations': {'Pet.S.C.': 'Pet.',
                        'Peters': 'Pet.',
                        'U.S.(Pet.)': 'Pet.',},
         'editions': {'Pet.': (date(1828, 1, 1), date(1842, 12, 31))},
         'mlz_jurisdiction': 'us'},
    'How.':
        {'name': 'Howard\'s Supreme Court Reports',
         'variations': {'U.S.(How.)': 'How.',},
         'editions': {'How.': (date(1843, 1, 1), date(1860, 12, 31))},
         'mlz_jurisdiction': 'us'},
    'Black':
        {'name': 'Black\'s Supreme Court Reports',
         'variations': {'Black R.': 'Black',
                        'U.S.(Black)': 'Black',},
         'editions': {'': (date(1861, 1, 1), date(1862, 12, 31))},
         'mlz_jurisdiction': 'us'},
    'Wall.':
        {'name': 'Wallace\'s Supreme Court Reports',
         'variations': {'U.S.(Wall.)': 'Wall.',
                        'Wall.Rep.': 'Wall.',
                        'Wall.S.C.': 'Wall.',},
         'editions': {'Wall.': (date(1863, 1, 1), date(1874, 12, 31))},
         'mlz_jurisdiction': 'us'},

    #####################
    # Federal Appellate #
    #####################
    'F.':
        {'name': 'Federal Reporter',
         'variations': {'F. 3d': 'F.3d',
                        'F. 2d': 'F.2d',
                        'Fed.R.': ('F.', 'F.2d', 'F.3d',),
                        'Fed.Rep.': ('F.', 'F.2d', 'F.3d',),},
         'editions': {'F.':   (date(1880, 1, 1), date(1924, 12, 31)),
                      'F.2d': (date(1924, 1, 1), date(1993, 12, 31)),
                      'F.3d': (date(1993, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    'F. Supp.':
        {'name': 'Federal Supplement',
         'variations': {'F.Supp.2d': 'F. Supp. 2d',
                        'F.Supp. 2d': 'F. Supp. 2d',
                        'F. Supp.2d': 'F. Supp. 2d',
                        'F.Supp.': 'F. Supp.'},
         'editions': {'F. Supp.':    (date(1932, 1, 1), date(1988, 12, 31)),
                      'F. Supp. 2d': (date(1988, 1, 1), date.today()),},
         'mlz_jurisdiction': 'us'},

    'Fed. Cl.':
        {'name': 'United States Claims Court Reporter',
         'variations': {},
         'editions': {'Fed. Cl.': (date(1992, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    'Ct. Cl.':
        {'name': 'Court of Claims Reports',
         'variations': {'Court Cl.': 'Ct. Cl.',
                        'Ct.Cl.': 'Ct. Cl.'},
         'editions': {'Ct. Cl.': (date(1863, 1, 1), date(1982, 12, 31))},
         'mlz_jurisdiction': 'us'},
    'B.R.':
        {'name': 'Bankruptcy Reporter',
         'variations': {},
         'editions': {'B.R.': (date(1979, 1, 1), date.today())},
         'mlz_jurisdiction': 'u.s.'},
    'T.C.':
        {'name': 'Reports of the United States Tax Court',
         'variations': {'T.Ct': 'T.C.',},
         'editions': {'T.C.': (date(1942, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    'M.J.':
        {'name': 'Military Justice Reporter',
         'variations': {},
         'editions': {'M.J.': (date(1975, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    # BB recommends no space here?
    'Vet. App.':
        {'name': 'Veterans Appeals Reporter',  # Apostrophe?
         'variations': {'Vet.App.': 'Vet. App.',},
         'editions': {'Vet. App.': (date(1990, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    'Ct. Int\'l Trade':
        {'name': 'Court of International Trade Reports',
         'variations': {'Ct.Int\'l Trade': 'Ct. Int\'l Trade',},
         'editions': {'Ct. Int\'l Trade': (date(1980, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    # BB recommends no space here?
    'F. Cas.':
        {'name': 'Federal Cases',
         'variations': {'F.C.':    'F. Cas.',
                        'F.Cas.':  'F. Cas.',
                        'Fed.Ca.': 'F. Cas.',},
         'editions': {'F. Cas.': (date(1789, 1, 1), date(1880, 1, 1)),},
         'mlz_jurisdiction': 'us'},

    ############################
    # State regional reporters #
    ############################
    'N.E.':
        {'name': 'North Eastern Reporter',
         'variations': {'N.E.Rep.': 'N.E.',
                        'NE': 'N.E.',
                        'No.East Rep.': 'N.E.',
                        'NE 2d': 'N.E.2d', },
         'editions': {'N.E.': (date(1884, 1, 1), date(1936, 12, 31)),
                      'N.E.2d': (date(1936, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    'A.':
        {'name': 'Atlantic Reporter',
         'variations': {'A.R.':   'A.',
                        'A.Rep.': 'A.',
                        'At.':    'A.',
                        'Atl.':   'A.',
                        'Atl.R.': 'A.',
                        'Atl.2d': 'A.2d',},
         'editions': {'A.': (date(1885, 1, 1), date(1938, 12, 31)),
                      'A.2d': (date(1938, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    'S.E.':
        {'name': 'South Eastern Reporter',
         'variations': {'SE': 'S.E.',
                        'SE 2d': 'S.E.2d'},
         'editions': {'S.E.': (date(1887, 1, 1), date(1939, 12, 31)),
                      'S.E.2d': (date(1939, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    'So.':
        {'name': 'Southern Reporter',
         'variations': {'South.': ('So.', 'So.2d'),
                        'So.2d': 'So. 2d',
                        'So.3d': 'So. 3d',},
         'editions': {'So.': (date(1886, 1, 1), date(1941, 12, 31)),
                      'So. 2d': (date(1941, 1, 1), date(2008, 12, 31)),
                      'So. 3d': (date(2008, 1, 1), date.today()),},
         'mlz_jurisdiction': 'us'},
    'S.W.':
        {'name': 'South Western Reporter',
         'variations': {'SW': 'S.W.',
                        'SW 2d': 'S.W.2d',
                        'SW 3d': 'S.W.3d',},
         'editions': {'S.W.': (date(1886, 1, 1), date(1928, 12, 31)),
                      'S.W.2d': (date(1928, 1, 1), date(1999, 12, 31))
                      'S.W.3d': (date(1999, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    'N.W.':
        {'name': 'North Western Reporter',
         'variations': {'No.West Rep.': 'N.W.',
                        'Northw.Rep.': 'N.W.',
                        'NW': 'N.W.',
                        'NW 2d': 'N.W.2d',},
         'editions': {'N.W.': (date(1880, 1, 1), date(1942, 12, 31)),
                      'N.W.2d': (date(1942, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},
    'P.':
        {'name': 'Pacific Reporter',
         'variations': {'P': 'P.',
                        'P.R.': 'P.',
                        'Pac.': 'P.',
                        'Pac.R.': 'P.',
                        'Pac.Rep.': 'P.',
                        'P. 2d': 'P.2d',
                        'P 2d': 'P.2d',
                        'P. 3d': 'P.3d',
                        'P 3d': 'P.3d',},
         'editions': {'P.':   (date(1883, 1, 1), date(1931, 12, 31)),
                      'P.2d': (date(1931, 1, 1), date(2000, 12, 31)),
                      'P.3d': (date(2000, 1, 1), date.today()),},
         'mlz_jurisdiction': 'us'},


    ###################
    # State reporters #
    ###################
    'Ala.':
        {'name': 'Alabama Reports',
         'variations': {},
         'editions': {'Ala.': (date(1840, 1, 1), date(1976, 12, 31)),
                      'Ala. 2d': (date(1977, 01, 01), date.today()),},
         'mlz_jurisdiction': 'us;al'},
    'Ala. App.':
        {'name': 'Alabama Appellate Courts Reports',
         'variations': {},
         'editions': {'Ala. App.': (date(1910, 1, 1), date(1976, 12, 31)),},
         'mlz_jurisdiction': 'us;al'},
    'Stew':
        {'name': 'Stewart',
         'variations': {'Stewart': 'Stew.'},
         'editions': {'Stew.': (date(1827, 1, 1), date(1831, 12, 31)),},
         'mlz_jurisdiction': 'us;al'},
    'Stew. & P.':
        {'name': 'Stewart and Porter',
         'variations': {},
         'editions': {'Stew. & P.': (date(1831, 1, 1), date(1834, 1, 1))},
         'mlz_jurisdiction': 'us;al'},
    'Port.':
        {'name': 'Porter\'s Alabama Reports',
         'variations': {},
         'editions': {'Port.': (date(1834, 1, 1), date(1839, 12, 31)),},
         'mlz_jurisdiction': 'us;al'},
    'Minor':
        {'name': 'Minor\'s Alabama Reports',
         'variations': {'Ala.': 'Minor',
                        'Min.': 'Minor',
                        'Minor (Ala.)': 'Minor'},
         'editions': {'Minor': (date(1820, 1, 1), date(1826, 1, 1)),},
         'mlz_jurisdiction': 'us;al'},

    'Alaska Fed.':
        {'name': 'Alaska Federal Reports',
         'variations': {'A.F.Rep.': 'Alaska Fed.',
                        'Alaska Fed.': 'Alaska Fed.',
                        'Alaska Fed.R.': 'Alaska Fed.',
                        'Alaska Fed.Rep.': 'Alaska Fed.', },
         'editions': {'Alaska Fed.': (date(1869, 1, 1), date(1937, 12, 31))},
         'mlz_jurisdiction': 'us;ak'},
    'Alaska':
        {'name': 'Alaska Reports',
         'variations': {'Alk.': 'Alaska',},
         'editions': {'Alaska': (date(1884, 1, 1), date(1959, 12, 31)),},
         'mlz_jurisdiction': 'us;ak'},

    'Ariz.':
        {'name': 'Arizona Reporter',
         'variations': {},
         'editions': {'Ariz.': (date(1866, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;az'},
    'Ariz. App.':
        {'name': 'Arizona Appeals Reports',
         'variations': {},
         'editions': {'Ariz. App.': (date(1965, 1, 1), date(1976, 12, 31))},
         'mlz_jurisdiction': 'us;az'},

    'Ark.':
        {'name': 'Arkansas Reports',
         'variations': {'Ak.': 'Ark.',},
         'editions': {'Ark.': (date(1837, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ar'},
    'Ark. App.':
        {'name': 'Arkansas Appellate Reports',
         'variations': {},
         'editions': {'Ark. App.': (date(1981, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ar'},

    'Cal.':
        {'name': 'California Reports',
         'variations': {'Cal.2d': 'Cal. 2d',
                        'Cal.3d': 'Cal. 3d',
                        'Cal.4th': 'Cal. 4th',},
         'editions': {'Cal.': (date(1850, 1, 1), date(1934, 12, 31)),
                      'Cal. 2d': (date(1934, 1, 1), date(1969, 12, 31)),
                      'Cal. 3d': (date(1969, 1, 1), date(1991, 12, 31)),
                      'Cal. 4th': (date(1991, 1, 1), date.today()),},
         'mlz_jurisdiction': 'us;ca'},
    'Cal. Rptr.':
        {'name': 'West\'s California Reporter',
         'variations': {'Cal.Rptr.': 'Cal. Rptr.',
                        'Cal.Rptr.2d': 'Cal. Rptr. 2d',
                        'Cal.Rptr.3d': 'Cal. Rptr. 3d',},
         'editions': {'Cal. Rptr.': (date(1959, 1, 1), date(1991, 12, 31)),
                      'Cal. Rptr. 2d': (date(1992, 1, 1), date(2003, 12, 31)),
                      'Cal. Rptr. 3d': (date(2003, 1, 1), date.today()),},
         'mlz_jurisdiction': 'us;ca'},
    'Cal. App.':
        {'name': 'California Appellate Reports',
         'variations': {'Cal.App.': 'Cal. App.',
                        'Cal.App.2d': 'Cal. App. 2d',
                        'Cal.App.3d': 'Cal. App. 3d',
                        'Cal.App.4th': 'Cal. App. 4th',},
         'editions': {'Cal. App.': (date(1905, 1, 1), date(1934, 12, 31)),
                      'Cal. App. 2d': (date(1934, 1, 1), date(1969, 12, 31)),
                      'Cal. App. 3d': (date(1969, 1, 1), date(1991, 12, 31)),
                      'Cal. App. 4th': (date(1991, 1, 1), date.today()),},
         'mlz_jurisdiction': 'us;ca'},
    'Cal. App. Supp.':
        {'name': 'California Appellate Reports, Supplement',
         'variations': {'Cal.App.Supp.': 'Cal. App. Supp.',},
         # Dates are unknown here.
         'editions': {'Cal. App. Supp.': (date(1929, 1, 1), date.today()),
                      'Cal. App. Supp. 2d': (date(1929, 1, 1), date.today()),
                      'Cal. App. Supp. 3d': (date(1929, 1, 1), date.today()),},
         'mlz_jurisdiction': 'us;ca'},
    'Cal. Unrep.':
        {'name': 'California Unreported Cases',
         'variations': {},
         'editions': {'Cal. Unrep.': (date(1855, 1, 1), date(1910, 12, 31))},
         'mlz_jurisdiction': ''},

    'Colo.':
        {'name': 'Colorado Reports',
         'variations': {},
         'editions': {'Colo.': (date(1864, 1, 1), date(1980, 12, 31))},
         'mlz_jurisdiction': 'us;co'},
    'Colo. Law.':
        {'name': 'Colorado Lawyer',
         'variations': {},
         'editions': {'Colo. Law.': (date(1750, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;co'},
    'Brief Times Rptr.':
        {'name': 'Brief Times Reporter',
         'variations': {},
         'editions': {'Brief Times Rptr': (date(1750, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;co'},

    'Kirby':
        {'name': 'Kirby\'s Connecticut Reports',
         'variations': {},
         'editions': {'Kirby': (date(1785, 1, 1), date(1789, 12, 31))},
         'mlz_jurisdiction': 'us;ct'},
    'Root':
        {'name': 'Root\s Connecticut Reports',
         'variations': {},
         'editions': {'Root': (date(1789, 1, 1), date(1798, 12, 31))},
         'mlz_jurisdiction': 'us;ct'},
    'Day':
        {'name': 'Day\'s Connecticut Reports',
         'variations': {},
         'editions': {'Day': (date(1802, 1, 1), date(1813, 12, 31))},
         'mlz_jurisdiction': 'uc;ct'},
    'Conn.':
        {'name': 'Connecticut Reports',
         'variations': {},
         'editions': {'Conn.': (date(1814, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ct'},
    'Conn. App.':
        {'name': 'Connecticut Appellate Reports',
         'variations': {},
         'editions': {'Conn. App.': (date(1983, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ct'},
    'Conn. Supp.':
        {'name': 'Connecticut Supplement',
         'variations': {},
         'editions': {'Conn. Supp.': (date(1935, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ct'},
    'Conn. L. Rptr.':
        {'name': 'Connecticut Law Reporter',
         'variations': {},
         'editions': {'Conn. L. Rptr': (date(1990, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ct'},
    'Conn. Super. Ct.':
        {'name': 'Connecticut Superior Court Reports',
         'variations': {},
         'editions': {'Conn. Super Ct.': (date(1986, 1, 1), date(1994, 12, 31))},
         'mlz_jurisdiction': 'us;ct'},
    'Conn. Cir. Ct':
        {'name': 'Connecticut Circuit Court Reports',
         'variations': {},
         'editions': {'Conn. Cir. Ct': (date(1961, 1, 1), date(1974, 12, 31))},
         'mlz_jurisdiction': 'us;ct'},

    'D.C.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Del.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Fla.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Ga. App.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Ga.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Haw.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Idaho':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Ill. Dec.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Ill. App. 3d':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Ill. App. 2d':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Ill. App.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Ill.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Ind.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Iowa':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Kan. App. 2d':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Kan. App.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Kan.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Ky.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'La.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Mass. App. Ct.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Mass.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Md. App.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Md.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Me.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Mich. App.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Mich.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Minn.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Miss.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Mo.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Mont.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'N.C. App.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'N.C.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'N.D.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'N.H.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'N.J. Tax':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'N.J. Super.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'N.J.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'N.M.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'N.Y.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'N.Y.':
        {'name': 'New York Reports',
         'variations': {},
         'editions': {'N.Y.': (date(1847, 1, 1), date(1956, 12, 31)),
                      'N.Y.2d': (date(1956, 1, 1), date(2004, 1, 1)),
                      'N.Y.3d': (date(2004, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ny'},
    'N.Y.S.':
    {'name': 'New York Supplement',
         'variations': {'New York Supp.': 'N.Y.S.',
                        'NYS': 'N.Y.S.',
                        'NYS 2d': 'N.Y.S.2d', },
         'editions': {'N.Y.S.': (date(1888, 1, 1), date(1937, 12, 31)),
                      'N.Y.S.2d': (date(1938, 1, 1), date())},
         'mlz_jurisdiction': 'us;ny'},
    'A.D.':
        {'name': 'New York Supreme Court Appellate Division Reports',
         'variations': {'Ap.': 'A.D.',
                        'App.Div.': 'A.D.',
                        'App.Div.(N.Y.)': 'A.D.',
                        'N.Y.App.Dec.': 'A.D.',
                        'N.Y.App.Div.': 'A.D.',
                        'Ap.2d.': 'A.D.',
                        'App.Div.2d.': 'A.D.', },
         'editions': {'A.D.': (date(1896, 1, 1), date(1955, 12, 31)),
                      # Dates are fuzzy here and thus have overlap.
                      # Best guess is based on: http://www.antiqbook.com/boox/law/57231.shtml
                      'A.D.2d': (date(1955, 1, 1), date(2004, 12, 31)),
                      'A.D.3d': (date(2003, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ny'},
    'Misc.':
        {'name': 'New York Miscellaneous Reports',
         'variations': {},
         'editions': {'Misc.': (date(1892, 1, 1), date(1955, 12, 31)),
                      'Misc. 2d': (date(1955, 1, 1), date(2004, 12, 31)), # http://www.antiqbook.com/boox/law/59388.shtml
                      'Misc. 3d': (date(2004, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ny'},

    'Neb. App.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Neb.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Nev.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Ohio':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},

    'Ohio St.':
        {'name': 'Ohio State Reports',
         'variations': {'O.S.': 'Ohio St.',
                        'Oh.St.': 'Ohio St.',
                        'O.S.2d': 'Ohio St. 2d',
                        'Ohio St.2d': 'Ohio St. 2d',
                        'O.S.3d': 'Ohio St. 3d',
                        'Ohio St.3d': 'Ohio St. 3d', },
         'editions': {'Ohio St.': (date(1840, 1, 1), date(1964, 12, 31)),
                      'Ohio St. 2d': (date(1965, 1, 1), date(1991, 12, 31)),
                      'Ohio St. 3d': (date(1991), date.today()), },
         'mlz_jurisdiction': 'us;oh'},

    'Okla.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Or.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Pa. Commw.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Pa. Super.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Pa.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'P.R.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'R.I.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'S.C.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'S.D.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Tenn.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Tex.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Utah':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Va. App.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Va.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Vt.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'W.Va.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Wash. Terr.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},  # Washington Territory Reports
    'Wash. App.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Wash. 2d':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Wash.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Wis. 2d':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Wis.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'Wyo.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},

    # Advance citations
    'Nev. Adv. Op. No.':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
    'NY Slip Op':
        {'name': '',
         'variations': {},
         'editions': {'': (date(1, 1, 1), date(1, 12, 31))},
         'mlz_jurisdiction': ''},
}

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





    # State
    'Cal.': (date(1850, 1, 1),
             date(1934, 12, 31)),
    'Cal. 2d': (date(1934, 1, 1),
                date(1969, 12, 31)),
    'Cal. 3d': (date(1969, 1, 1),
                date(1991, 12, 31)),
    'Cal. 4th': (date(1991, 1, 1),
                 date.today()),

}
