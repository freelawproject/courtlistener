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
        [{'name': 'United States Supreme Court Reports',
         'variations': {'U.S.S.C.Rep.': 'U.S.',
                        'USSCR': 'U.S.',
                        'U. S.': 'U.S.'},
         'editions': {'U.S.': (date(1790, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'S. Ct.':
        [{'name': 'West\'s Supreme Court Reporter',
         'variations': {'S Ct': 'S. Ct.',
                        'S.C.': 'S. Ct.',
                        'S.Ct.': 'S. Ct.',
                        'Sup.Ct.': 'S. Ct.',
                        'Sup.Ct.Rep.': 'S. Ct.',
                        'Supr.Ct.Rep.': 'S. Ct.', },
         'editions': {'S. Ct.': (date(1882, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'L. Ed.':
        [{'name': 'Lawyer\'s Edition',
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
                        'L.Ed. 2d': 'L. Ed. 2d',
                        'L. Ed.2d': 'L. Ed. 2d',
                        'U.S.L.Ed.2d': 'L. Ed. 2d', },
         'editions': {'L. Ed.': (date(1790, 1, 1), date(1956, 12, 31)),
                      'L. Ed. 2d': (date(1956, 1, 1), date.today()), },
         'mlz_jurisdiction': 'us'},],
    'Dall.': [{'name': 'Dallas\' Supreme Court Reports',
               'variations': {'Dal.': 'Dall.',
                              'Dall.S.C.': 'Dall.',
                              'Dallas': 'Dall.',
                              'U.S.(Dall.)': 'Dall.'},
               'editions': {'Dall': (date(1790, 1, 1), date(1880, 12, 31))},
               'mlz_jurisdiction': 'us'},
              {'name': 'Pennsylvania State Reports, Dallas',
               'variations': {},
               'editions': {'Dall.': (date(1754, 1, 1), date(1806, 12, 31))},
               'mlz_jurisdiction': 'us;pa'}, ],
    'Cranch': [{'name': 'Cranch\'s Supreme Court Reports',
                'variations': {'Cr.': 'Cranch',
                               'Cra.': 'Cranch',
                               'Cranch (US)': 'Cranch',
                               'U.S.(Cranch)': 'Cranch'},
                'editions': {'Cranch': (date(1801, 1, 1), date(1815, 12, 31))},
                'mlz_jurisdiction': 'us'},
               {'name': 'District of Columbia Reports, Cranch',
                'variations': {},
                'editions': {'Cranch': (date(1801, 1, 1), date(1841, 12, 31))},
                'mlz_jurisdiction': 'us;dc'}, ],
    'Wheat.':
        [{'name': 'Wheaton\'s Supreme Court Reports',
         'variations': {'U.S.(Wheat.)': 'Wheat.',
                        'Wheaton': 'Wheat.', },
         'editions': {'Wheat': (date(1816, 1, 1), date(1827, 12, 31))},
         'mlz_jurisdiction': 'us'},],
    'Pet.':
        [{'name': 'Peters\' Supreme Court Reports',
         'variations': {'Pet.S.C.': 'Pet.',
                        'Peters': 'Pet.',
                        'U.S.(Pet.)': 'Pet.', },
         'editions': {'Pet.': (date(1828, 1, 1), date(1842, 12, 31))},
         'mlz_jurisdiction': 'us'},],
    'How.':
        [{'name': 'Howard\'s Supreme Court Reports',
         'variations': {'U.S.(How.)': 'How.', },
         'editions': {'How.': (date(1843, 1, 1), date(1860, 12, 31))},
         'mlz_jurisdiction': 'us'},],
    'Black':
        [{'name': 'Black\'s Supreme Court Reports',
         'variations': {'Black R.': 'Black',
                        'U.S.(Black)': 'Black', },
         'editions': {'': (date(1861, 1, 1), date(1862, 12, 31))},
         'mlz_jurisdiction': 'us'},],
    'Wall.':
        [{'name': 'Wallace\'s Supreme Court Reports',
         'variations': {'U.S.(Wall.)': 'Wall.',
                        'Wall.Rep.': 'Wall.',
                        'Wall.S.C.': 'Wall.', },
         'editions': {'Wall.': (date(1863, 1, 1), date(1874, 12, 31))},
         'mlz_jurisdiction': 'us'},],

    #####################
    # Federal Appellate #
    #####################
    'F.':
        [{'name': 'Federal Reporter',
         'variations': {'F. 3d': 'F.3d',
                        'F. 2d': 'F.2d',
                        'Fed.R.': ('F.', 'F.2d', 'F.3d',),
                        'Fed.Rep.': ('F.', 'F.2d', 'F.3d',), },
         'editions': {'F.': (date(1880, 1, 1), date(1924, 12, 31)),
                      'F.2d': (date(1924, 1, 1), date(1993, 12, 31)),
                      'F.3d': (date(1993, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'F. Supp.':
        [{'name': 'Federal Supplement',
         'variations': {'F.Supp.2d': 'F. Supp. 2d',
                        'F.Supp. 2d': 'F. Supp. 2d',
                        'F. Supp.2d': 'F. Supp. 2d',
                        'F.Supp.': 'F. Supp.'},
         'editions': {'F. Supp.': (date(1932, 1, 1), date(1988, 12, 31)),
                      'F. Supp. 2d': (date(1988, 1, 1), date.today()), },
         'mlz_jurisdiction': 'us'},],
    'Fed. Cl.':
        [{'name': 'United States Claims Court Reporter',
         'variations': {'Fed.Cl.': 'Fed. Cl.', },
         'editions': {'Fed. Cl.': (date(1992, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'Ct. Cl.':
        [{'name': 'Court of Claims Reports',
         'variations': {'Court Cl.': 'Ct. Cl.',
                        'Ct.Cl.': 'Ct. Cl.'},
         'editions': {'Ct. Cl.': (date(1863, 1, 1), date(1982, 12, 31))},
         'mlz_jurisdiction': 'us'},],
    'B.R.':
        [{'name': 'Bankruptcy Reporter',
         'variations': {'B. R.': 'B.R.',
                        'BR': 'B.R.', },
         'editions': {'B.R.': (date(1979, 1, 1), date.today())},
         'mlz_jurisdiction': 'u.s.'},],
    'T.C.':
        [{'name': 'Reports of the United States Tax Court',
         'variations': {'T.Ct': 'T.C.',
                        'T. C.': 'T.C.', },
         'editions': {'T.C.': (date(1942, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'M.J.':
        [{'name': 'Military Justice Reporter',
         'variations': {'M. J.': 'M.J.', },
         'editions': {'M.J.': (date(1975, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    # BB recommends no space here?
    'Vet. App.':
        [{'name': 'Veterans Appeals Reporter', # Apostrophe?
         'variations': {'Vet.App.': 'Vet. App.', },
         'editions': {'Vet. App.': (date(1990, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'Ct. Int\'l Trade':
        [{'name': 'Court of International Trade Reports',
         'variations': {'Ct.Int\'l Trade': 'Ct. Int\'l Trade'},
         'editions': {'Ct. Int\'l Trade': (date(1980, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    # BB recommends no space here?
    'F. Cas.':
        [{'name': 'Federal Cases',
         'variations': {'F.C.': 'F. Cas.',
                        'F.Cas.': 'F. Cas.',
                        'Fed.Ca.': 'F. Cas.', },
         'editions': {'F. Cas.': (date(1789, 1, 1), date(1880, 1, 1)), },
         'mlz_jurisdiction': 'us'},],

    ############################
    # State regional reporters #
    ############################
    'N.E.':
        [{'name': 'North Eastern Reporter',
         'variations': {'N. E.': 'N.E.',
                        'N.E.Rep.': 'N.E.',
                        'NE': 'N.E.',
                        'No.East Rep.': 'N.E.',
                        'NE 2d': 'N.E.2d',
                        'N. E. 2d': 'N.E.2d',
                        'N.E. 2d': 'N.E.2d',
                        'N. E.2d': 'N.E.2d', },
         'editions': {'N.E.': (date(1884, 1, 1), date(1936, 12, 31)),
                      'N.E.2d': (date(1936, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'A.':
        [{'name': 'Atlantic Reporter',
         'variations': {'A.R.': 'A.',
                        'A.Rep.': 'A.',
                        'At.': 'A.',
                        'Atl.': 'A.',
                        'Atl.R.': 'A.',
                        'A. 2d': 'A.2d',
                        'A. 3d': 'A.3d',
                        'Atl.2d': 'A.2d', },
         'editions': {'A.': (date(1885, 1, 1), date(1938, 12, 31)),
                      'A.2d': (date(1938, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'S.E.':
        [{'name': 'South Eastern Reporter',
         'variations': {'SE': 'S.E.',
                        'SE 2d': 'S.E.2d',
                        'S.E. 2d': 'S.E.2d',
                        'S. E. 2d': 'S.E.2d',
                        'S. E.2d': 'S.E.2d',
                        'S. E.': 'S.E.', },
         'editions': {'S.E.': (date(1887, 1, 1), date(1939, 12, 31)),
                      'S.E.2d': (date(1939, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'So.':
        [{'name': 'Southern Reporter',
         'variations': {'South.': ('So.', 'So.2d'),
                        'So.2d': 'So. 2d',
                        'So.3d': 'So. 3d', },
         'editions': {'So.': (date(1886, 1, 1), date(1941, 12, 31)),
                      'So. 2d': (date(1941, 1, 1), date(2008, 12, 31)),
                      'So. 3d': (date(2008, 1, 1), date.today()), },
         'mlz_jurisdiction': 'us'},],
    'S.W.':
        [{'name': 'South Western Reporter',
         'variations': {'SW': 'S.W.',
                        'SW 2d': 'S.W.2d',
                        'SW 3d': 'S.W.3d',
                        'S. W. 2d': 'S.W.2d',
                        'S.W. 2d': 'S.W.2d',
                        'S. W.2d': 'S.W.2d',
                        'S. W. 3d': 'S.W.3d',
                        'S.W. 3d': 'S.W.3d',
                        'S. W.3d': 'S.W.3d',
                        'S. W.': 'S.W.'},
         'editions': {'S.W.': (date(1886, 1, 1), date(1928, 12, 31)),
                      'S.W.2d': (date(1928, 1, 1), date(1999, 12, 31)),
                      'S.W.3d': (date(1999, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'N.W.':
        [{'name': 'North Western Reporter',
         'variations': {'No.West Rep.': 'N.W.',
                        'Northw.Rep.': 'N.W.',
                        'NW': 'N.W.',
                        'NW 2d': 'N.W.2d',
                        'N. W. 2d': 'N.W.2d',
                        'N.W. 2d': 'N.W.2d',
                        'N. W.2d': 'N.W.2d',
                        'N. W.': 'N.W.'},
         'editions': {'N.W.': (date(1880, 1, 1), date(1942, 12, 31)),
                      'N.W.2d': (date(1942, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'P.':
        [{'name': 'Pacific Reporter',
         'variations': {'P': 'P.',
                        'P.R.': 'P.',
                        'Pac.': 'P.',
                        'Pac.R.': 'P.',
                        'Pac.Rep.': 'P.',
                        'P. 2d': 'P.2d',
                        'P 2d': 'P.2d',
                        'P. 3d': 'P.3d',
                        'P 3d': 'P.3d', },
         'editions': {'P.': (date(1883, 1, 1), date(1931, 12, 31)),
                      'P.2d': (date(1931, 1, 1), date(2000, 12, 31)),
                      'P.3d': (date(2000, 1, 1), date.today()), },
         'mlz_jurisdiction': 'us'},],


    ###################
    # State reporters #
    ###################
    'Ala.':
        [{'name': 'Alabama Reports',
         'variations': {},
         'editions': {'Ala.': (date(1840, 1, 1), date(1976, 12, 31)),
                      'Ala. 2d': (date(1977, 01, 01), date.today()), },
         'mlz_jurisdiction': 'us;al'},],
    'Ala. App.':
        [{'name': 'Alabama Appellate Courts Reports',
         'variations': {},
         'editions': {'Ala. App.': (date(1910, 1, 1), date(1976, 12, 31)), },
         'mlz_jurisdiction': 'us;al'},],
    'Stew':
        [{'name': 'Stewart',
         'variations': {'Stewart': 'Stew.'},
         'editions': {'Stew.': (date(1827, 1, 1), date(1831, 12, 31)), },
         'mlz_jurisdiction': 'us;al'},],
    'Stew. & P.':
        [{'name': 'Stewart and Porter',
         'variations': {},
         'editions': {'Stew. & P.': (date(1831, 1, 1), date(1834, 1, 1))},
         'mlz_jurisdiction': 'us;al'},],
    'Port.':
        [{'name': 'Porter\'s Alabama Reports',
         'variations': {},
         'editions': {'Port.': (date(1834, 1, 1), date(1839, 12, 31)), },
         'mlz_jurisdiction': 'us;al'},],
    'Minor':
        [{'name': 'Minor\'s Alabama Reports',
         'variations': {'Ala.': 'Minor',
                        'Min.': 'Minor',
                        'Minor (Ala.)': 'Minor'},
         'editions': {'Minor': (date(1820, 1, 1), date(1826, 1, 1)), },
         'mlz_jurisdiction': 'us;al'},],

    'Alaska Fed.':
        [{'name': 'Alaska Federal Reports',
         'variations': {'A.F.Rep.': 'Alaska Fed.',
                        'Alaska Fed.': 'Alaska Fed.',
                        'Alaska Fed.R.': 'Alaska Fed.',
                        'Alaska Fed.Rep.': 'Alaska Fed.', },
         'editions': {'Alaska Fed.': (date(1869, 1, 1), date(1937, 12, 31))},
         'mlz_jurisdiction': 'us;ak'},],
    'Alaska':
        [{'name': 'Alaska Reports',
         'variations': {'Alk.': 'Alaska', },
         'editions': {'Alaska': (date(1884, 1, 1), date(1959, 12, 31))},
         'mlz_jurisdiction': 'us;ak'},],

    'Ariz.':
        [{'name': 'Arizona Reporter',
         'variations': {},
         'editions': {'Ariz.': (date(1866, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;az'},],
    'Ariz. App.':
        [{'name': 'Arizona Appeals Reports',
         'variations': {},
         'editions': {'Ariz. App.': (date(1965, 1, 1), date(1976, 12, 31))},
         'mlz_jurisdiction': 'us;az'},],

    'Ark.':
        [{'name': 'Arkansas Reports',
         'variations': {'Ak.': 'Ark.', },
         'editions': {'Ark.': (date(1837, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ar'},],
    'Ark. App.':
        [{'name': 'Arkansas Appellate Reports',
         'variations': {},
         'editions': {'Ark. App.': (date(1981, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ar'},],

    'Cal.':
        [{'name': 'California Reports',
         'variations': {'Cal.2d': 'Cal. 2d',
                        'Cal.3d': 'Cal. 3d',
                        'Cal.4th': 'Cal. 4th', },
         'editions': {'Cal.': (date(1850, 1, 1), date(1934, 12, 31)),
                      'Cal. 2d': (date(1934, 1, 1), date(1969, 12, 31)),
                      'Cal. 3d': (date(1969, 1, 1), date(1991, 12, 31)),
                      'Cal. 4th': (date(1991, 1, 1), date.today()), },
         'mlz_jurisdiction': 'us;ca'},],
    'Cal. Rptr.':
        [{'name': 'West\'s California Reporter',
         'variations': {'Cal.Rptr.': 'Cal. Rptr.',
                        'Cal.Rptr.2d': 'Cal. Rptr. 2d',
                        'Cal.Rptr.3d': 'Cal. Rptr. 3d',
                        'Cal.Rptr. 3d': 'Cal. Rptr. 3d',
                        'Cal. Rptr.3d': 'Cal. Rptr. 3d',
                        'Cal.Rptr. 2d': 'Cal. Rptr. 2d',
                        'Cal. Rptr.2d': 'Cal. Rptr. 2d', },
         'editions': {'Cal. Rptr.': (date(1959, 1, 1), date(1991, 12, 31)),
                      'Cal. Rptr. 2d': (date(1992, 1, 1), date(2003, 12, 31)),
                      'Cal. Rptr. 3d': (date(2003, 1, 1), date.today()), },
         'mlz_jurisdiction': 'us;ca'},],
    'Cal. App.':
        [{'name': 'California Appellate Reports',
         'variations': {'Cal.App.': 'Cal. App.',
                        'Cal.App.2d': 'Cal. App. 2d',
                        'Cal.App.3d': 'Cal. App. 3d',
                        'Cal.App.4th': 'Cal. App. 4th',
                        'Cal. App.4th': 'Cal. App. 4th',
                        'Cal.App. 4th': 'Cal. App. 4th',
                        'Cal. App.3d': 'Cal. App. 3d',
                        'Cal.App. 3d': 'Cal. App. 3d',
                        'Cal. App.2d': 'Cal. App. 2d',
                        'Cal.App. 2d': 'Cal. App. 2d', },
         'editions': {'Cal. App.': (date(1905, 1, 1), date(1934, 12, 31)),
                      'Cal. App. 2d': (date(1934, 1, 1), date(1969, 12, 31)),
                      'Cal. App. 3d': (date(1969, 1, 1), date(1991, 12, 31)),
                      'Cal. App. 4th': (date(1991, 1, 1), date.today()), },
         'mlz_jurisdiction': 'us;ca'},],
    'Cal. App. Supp.':
        [{'name': 'California Appellate Reports, Supplement',
         'variations': {'Cal.App.Supp.': 'Cal. App. Supp.',
                        'Cal.App.3d Supp.': 'Cal. App. Supp. 3d', # People get the order of these wrong.
                        'Cal.App. 3d Supp.': 'Cal. App. Supp. 3d',
                        'Cal.App.2d Supp.': 'Cal. App. Supp. 2d',
                        'Cal.App. 2d Supp.': 'Cal. App. Supp. 2d',
                        'Cal.App. Supp. 3d': 'Cal. App. Supp. 3d', # These are the correct order (wrong spacing).
                        'Cal.App. Supp.3d': 'Cal. App. Supp. 3d',
                        'Cal.App. Supp. 2d': 'Cal. App. Supp. 2d',
                        'Cal.App. Supp.2d': 'Cal. App. Supp. 2d', },
         # Dates need more research.
         'editions': {'Cal. App. Supp.': (date(1929, 1, 1), date.today()),
                      'Cal. App. Supp. 2d': (date(1929, 1, 1), date.today()),
                      'Cal. App. Supp. 3d': (date(1929, 1, 1), date.today()), },
         'mlz_jurisdiction': 'us;ca'},],
    'Cal. Unrep.':
        [{'name': 'California Unreported Cases',
         'variations': {},
         'editions': {'Cal. Unrep.': (date(1855, 1, 1), date(1910, 12, 31))},
         'mlz_jurisdiction': 'us;ca'},],

    'Colo.':
        [{'name': 'Colorado Reports',
         'variations': {},
         'editions': {'Colo.': (date(1864, 1, 1), date(1980, 12, 31))},
         'mlz_jurisdiction': 'us;co'},],
    'Colo. Law.':
        [{'name': 'Colorado Lawyer',
         'variations': {},
         'editions': {'Colo. Law.': (date(1750, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;co'},],
    'Brief Times Rptr.':
        [{'name': 'Brief Times Reporter',
         'variations': {},
         'editions': {'Brief Times Rptr': (date(1750, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;co'},],

    'Kirby':
        [{'name': 'Kirby\'s Connecticut Reports',
         'variations': {},
         'editions': {'Kirby': (date(1785, 1, 1), date(1789, 12, 31))},
         'mlz_jurisdiction': 'us;ct'},],
    'Root':
        [{'name': 'Root\s Connecticut Reports',
         'variations': {},
         'editions': {'Root': (date(1789, 1, 1), date(1798, 12, 31))},
         'mlz_jurisdiction': 'us;ct'},],
    'Day':
        [{'name': 'Day\'s Connecticut Reports',
         'variations': {},
         'editions': {'Day': (date(1802, 1, 1), date(1813, 12, 31))},
         'mlz_jurisdiction': 'uc;ct'},],
    'Conn.':
        [{'name': 'Connecticut Reports',
         'variations': {},
         'editions': {'Conn.': (date(1814, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ct'},],
    'Conn. App.':
        [{'name': 'Connecticut Appellate Reports',
         'variations': {},
         'editions': {'Conn. App.': (date(1983, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ct'},],
    'Conn. Supp.':
        [{'name': 'Connecticut Supplement',
         'variations': {},
         'editions': {'Conn. Supp.': (date(1935, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ct'},],
    'Conn. L. Rptr.':
        [{'name': 'Connecticut Law Reporter',
         'variations': {},
         'editions': {'Conn. L. Rptr': (date(1990, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ct'},],
    'Conn. Super. Ct.':
        [{'name': 'Connecticut Superior Court Reports',
         'variations': {},
         'editions': {'Conn. Super Ct.': (date(1986, 1, 1), date(1994, 12, 31))},
         'mlz_jurisdiction': 'us;ct'},],
    'Conn. Cir. Ct':
        [{'name': 'Connecticut Circuit Court Reports',
         'variations': {},
         'editions': {'Conn. Cir. Ct': (date(1961, 1, 1), date(1974, 12, 31))},
         'mlz_jurisdiction': 'us;ct'},],

    'Harrington':
        [{'name': 'Harrington',
         'variations': {},
         'editions': {'Harrington': (date(1832, 1, 1), date(1855, 12, 31))},
         'mlz_jurisdiction': 'us;de'},],
    'Houston':
        [{'name': 'Houston',
         'variations': {},
         'editions': {'Houston': (date(1855, 1, 1), date(1893, 12, 31))},
         'mlz_jurisdiction': 'us;de'},],
    'Marvel':
        [{'name': 'Marvel',
         'variations': {},
         'editions': {'Marvel': (date(1893, 1, 1), date(1897, 12, 31))},
         'mlz_jurisdiction': 'us;de'},],
    'Pennewill':
        [{'name': 'Pennewill',
         'variations': {},
         'editions': {'Pennewill': (date(1897, 1, 1), date(1909, 12, 31))},
         'mlz_jurisdiction': 'us;de'},],
    'Boyce':
        [{'name': 'Boyce',
         'variations': {},
         'editions': {'Boyce': (date(1909, 1, 1), date(1920, 12, 31))},
         'mlz_jurisdiction': 'us;de'},],
    'Del.':
        [{'name': 'Delaware Reports',
         'variations': {},
         'editions': {'Del.': (date(1920, 1, 1), date(1966, 12, 31))},
         'mlz_jurisdiction': 'us;de'},],
    'Del. Cas.':
        [{'name': 'Delaware Cases',
         'variations': {},
         'editions': {'Del. Cas.': (date(1792, 1, 1), date(1830, 12, 31))},
         'mlz_jurisdiction': ''},],
    'Del. Ch.':
        [{'name': 'Delaware Chancery Reports',
         'variations': {},
         'editions': {'Del. Ch.': (date(1814, 1, 1), date(1968, 12, 31))},
         'mlz_jurisdiction': 'us;de'},],

    'U.S. App. D.C.':
        [{'name': 'United States Court of Appeals Reports',
         'variations': {},
         'editions': {'U.S. App. D.C.': (date(1941, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;dc'},],
    'App. D.C.':
        [{'name': 'Appeal Cases, District of Colombia',
         'variations': {},
         'editions': {'App. D.C.': (date(1893, 1, 1), date(1941, 12, 31))},
         'mlz_jurisdiction': 'us;dc'},],
    # See 'Cranch' key for additional DC reporter

    'Hay. & Haz.':
        [{'name': 'District of Columbia Reports, Hayward & Hazelton',
         'variations': {},
         'editions': {'Hay. & Haz.': (date(1841, 1, 1), date(1862, 12, 31))},
         'mlz_jurisdiction': 'us;dc'},],
    'Mackey':
        [{'name': 'District of Columbia Reports, Mackey',
         'variations': {},
         'editions': {'Mackey': (date(1863, 1, 1), date(1892, 12, 31)), }, # Gap from 1872 to 1880
         'mlz_jurisdiction': 'us;dc'},],
    'MacArth.':
        [{'name': 'District of Columbia Reports, MacArthur',
         'variations': {},
         'editions': {'MacArth.': (date(1873, 1, 1), date(1879, 12, 31))},
         'mlz_jurisdiction': 'us;dc'},],
    'MacArth. & M.':
        [{'name': 'District of Columbia Reports, MacArthur and Mackey',
         'variations': {},
         'editions': {'MacArth. & M.': (date(1879, 1, 1), date(1880, 12, 31))},
         'mlz_jurisdiction': 'us;dc'},],
    'Tuck. & Cl.':
        [{'name': 'District of Columbia Reports, Tucker and Clephane',
         'variations': {},
         'editions': {'Tuck. & Cl.': (date(1892, 1, 1), date(1893, 12, 31))},
         'mlz_jurisdiction': 'us;dc'},],

    'Fla.':
        [{'name': 'Florida Reports',
         'variations': {},
         'editions': {'Fla.': (date(1846, 1, 1), date(1948, 12, 31))},
         'mlz_jurisdiction': 'us;fl'},],
    'Fla. L. Weekly':
        [{'name': 'Florida Law Weekly',
         'variations': {},
         'editions': {'Fla. L. Weekly': (date(1978, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;fl'},],
    'Fla. Supp.':
        [{'name': 'Florida Supplement',
         'variations': {},
         'editions': {'Fla. Supp.': (date(1948, 1, 1), date(1981, 12, 31)),
                      'Fla. Supp. 2d': (date(1983, 1, 1), date(1992, 12, 31))},
         'mlz_jurisdiction': 'us;fl'},],
    'Fla. L. Weekly Supp.':
        [{'name': 'Florida Law Weekly Supplement',
         'variations': {},
         'editions': {'Fla. L. Weekly Supp.': (date(1992, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;fl'},],

    'Ga.':
        [{'name': 'Georgia Reports',
         'variations': {},
         'editions': {'Ga.': (date(1846, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ga'},],
    'Ga. App.':
        [{'name': 'Georgia Appeals Reports',
         'variations': {},
         'editions': {'Ga. App.': (date(1907, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ga'},],

    'Haw.':
        [{'name': 'Hawaii Reports',
         'variations': {},
         'editions': {'Haw.': (date(1847, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;hi'},],
    'Haw. App.':
        [{'name': 'Hawaii Appellate Reports',
         'variations': {},
         'editions': {'Haw. App.': (date(1980, 1, 1), date(1994, 12, 31))},
         'mlz_jurisdiction': 'us;hi'},],

    'Idaho':
        [{'name': 'Idaho Reports',
         'variations': {},
         'editions': {'Idaho': (date(1982, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;id'},],

    'Ill. Dec.':
        [{'name': 'West\'s Illinois Decisions',
         'variations': {'Ill.Dec.': 'Ill. Dec.', },
         'editions': {'Ill. Dec.': (date(1976, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;il'},],
    'Ill. App.':
        [{'name': 'Illinois Appellate Court Reports',
         'variations': {'Ill. App.3d': 'Ill. App. 3d',
                        'Ill. App.2d': 'Ill. App. 2d', },
         # needs research
         'editions': {'Ill. App.': (date(1877, 1, 1), date.today()),
                      'Ill. App. 2d': (date(1877, 1, 1), date.today()),
                      'Ill. App. 3d': (date(1877, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;il'},],
    'Ill. Ct. Cl.':
        [{'name': 'Illinois Court of Claims Reports',
         'variations': {},
         'editions': {'Ill. Ct. Cl.': (date(1889, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;il'},],
    'Breese':
        [{'name': 'Illinois Reports, Breese',
         'variations': {},
         'editions': {'Breese': (date(1819, 1, 1), date(1831, 12, 31))},
         'mlz_jurisdiction': 'us;il'},],
    'Scam.':
        [{'name': 'Illinois Reports, Scammon',
         'variations': {},
         'editions': {'Scam.': (date(1832, 1, 1), date(1843, 12, 31))},
         'mlz_jurisdiction': 'us;il'},],
    'Gilm.':
        [{'name': 'Illinois Reports, Gilman',
         'variations': {},
         'editions': {'Gilm.': (date(1844, 1, 1), date(1849, 12, 31))},
         'mlz_jurisdiction': 'us;il'},],
    'Ill.':
        [{'name': 'Illinois Reports',
         'variations': {},
         'editions': {'Ill.': (date(1849, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;il'},],


    'Ind.':
        [{'name': 'Indiana Reports',
         'variations': {},
         'editions': {'Ind.': (date(1848, 1, 1), date(1981, 12, 31))},
         'mlz_jurisdiction': 'us;in'},],
    'Blackf.':
        [{'name': 'Indiana Reports, Blackford',
         'variations': {},
         'editions': {'Blackf.': (date(1817, 1, 1), date(1847, 12, 31))},
         'mlz_jurisdiction': 'us;in'},],
    'Ind. App.':
        [{'name': 'Indiana Court of Appeals Reports',
         'variations': {},
         'editions': {'Ind. App.': (date(1890, 1, 1), date(1979, 12, 31))},
         'mlz_jurisdiction': 'us;in'},],

    'Bradf.':
        [{'name': 'Iowa Reports, Bradford',
         'variations': {},
         'editions': {'Bradf.': (date(1838, 1, 1), date(1841, 12, 31))},
         'mlz_jurisdiction': 'us;ia'},],
    'Morris':
        [{'name': 'Iowa Reports, Morris',
         'variations': {},
         'editions': {'Morris': (date(1839, 1, 1), date(1846, 12, 31))},
         'mlz_jurisdiction': 'us;ia'},],
    'Greene':
        [{'name': 'Iowa Reports, Greene',
         'variations': {},
         'editions': {'Greene': (date(1847, 1, 1), date(1854, 12, 31))},
         'mlz_jurisdiction': 'ui;ia'},],
    'Iowa':
        [{'name': 'Iowa Reports',
         'variations': {},
         'editions': {'Iowa': (date(1855, 1, 1), date(1968, 12, 31))},
         'mlz_jurisdiction': 'us;ia'},],

    'McCahon':
        [{'name': 'Kansas Reports, McCahon',
         'variations': {},
         'editions': {'McCahon': (date(1858, 1, 1), date(1868, 12, 31))},
         'mlz_jurisdiction': 'us;ks'},],
    'Kan.':
        [{'name': 'Kansas Reports',
         'variations': {},
         'editions': {'Kan.': (date(1862, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ks'},],
    'Kan. App.':
        [{'name': 'Kansas Court of Appeals Reports',
         'variations': {'Kan.App.2d': 'Kan. App. 2d',
                        'Kan.App. 2d': 'Kan. App. 2d',
                        'Kan. App.2d': 'Kan. App. 2d',
                        'Kan.App.': 'Kan. App.', },
         # These dates *are* from the Bluebook.
         'editions': {'Kan. App.': (date(1895, 1, 1), date(1901, 12, 31)),
                      'Kan. App. 2d': (date(1977, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ks'},],

    'Hughes': [{'name': 'Kentucky Reports, Hughes',
               'variations': {},
               'editions': {'Hughes': (date(1785, 1, 1), date(1801, 12, 31))},
               'mlz_jurisdiction': 'us;ky'},],
    'Sneed': [{'name': 'Kentucky Reports, Sneed',
               'variations': {},
               'editions': {'Sneed': (date(1801, 1, 1), date(1805, 12, 31))},
               'mlz_jurisdiction': 'us;ky'},
              {'name': 'Tennessee Reports, Sneed',
               'variations': {},
               'editions': {'Sneed': (date(1853, 1, 1), date(1858, 12, 31))},
               'mlz_jurisdiction': 'us;tn'}, ],
    'Hard.':
        [{'name': 'Kentucky Reports, Hardin',
         'variations': {},
         'editions': {'Hard.': (date(1805, 1, 1), date(1808, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Bibb':
        [{'name': 'Kentucky Reports, Bibb',
         'variations': {},
         'editions': {'Bibb': (date(1808, 1, 1), date(1817, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'A.K. Marsh.':
        [{'name': 'Kentucky Reports, Marshall, A.K.',
         'variations': {},
         'editions': {'A.K. Marsh.': (date(1817, 1, 1), date(1821, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Litt. Sel. Cas.':
        [{'name': 'Kentucky Reports, Littell\'s Selected Cases',
         'variations': {},
         'editions': {'Litt. Sel. Cas.': (date(1795, 1, 1), date(1821, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Litt.':
        [{'name': 'Kentucky Reports, Littell',
         'variations': {},
         'editions': {'Litt.': (date(1822, 1, 1), date(1824, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'T.B. Mon.':
        [{'name': 'Kentucky Reports, Monroe, T.B.',
         'variations': {},
         'editions': {'T.B. Mon.': (date(1824, 1, 1), date(1828, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'J.J. Marsh.':
        [{'name': 'Kentucky Reports, Marshall, J.J.',
         'variations': {},
         'editions': {'J.J. Marsh.': (date(1829, 1, 1), date(1832, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Dana':
        [{'name': 'Kentucky Reports, Dana',
         'variations': {},
         'editions': {'Dana': (date(1833, 1, 1), date(1840, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'B. Mon.':
        [{'name': 'Kentucky Reports, Monroe, Ben',
         'variations': {},
         'editions': {'B. Mon.': (date(1840, 1, 1), date(1857, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Met.': [{'name': 'Kentucky Reports, Metcalf',
              'variations': {},
              'editions': {'Met.': (date(1858, 1, 1), date(1863, 12, 31))},
              'mlz_jurisdiction': 'us;ky'},
             {'name': 'Massachusetts Reports, Metcalf',
              'variations': {},
              'editions': {'Met.': (date(1840, 1, 1), date(1847, 12, 31))},
              'mlz_jurisdiction': 'us;ma'},],
    'Duv.':
        [{'name': 'Kentucky Reports, Duvall',
         'variations': {},
         'editions': {'Duv.': (date(1863, 1, 1), date(1866, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Bush':
        [{'name': 'Kentucky Reports, Bush',
         'variations': {},
         'editions': {'Bush': (date(1866, 1, 1), date(1879, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Ky.':
        [{'name': 'Kentucky Reports',
         'variations': {},
         'editions': {'Ky.': (date(1879, 1, 1), date(1951, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Ky. Op.':
        [{'name': 'Kentucky Opinions',
         'variations': {},
         'editions': {'Ky. Op.': (date(1864, 1, 1), date(1886, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Ky. L. Rptr.':
        [{'name': 'Kentucky Law Reporter',
         'variations': {},
         'editions': {'Ky. L. Rptr.': (date(1880, 1, 1), date(1908, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Ky. App.':
        [{'name': 'Kentucky Appellate Reporter',
         'variations': {},
         'editions': {'Ky. App.': (date(1994, 1, 1), date(2000, 12, 31))},
         'mlz_jurisdiction': 'us;ky'},],
    'Ky. L. Summ.':
        [{'name': 'Kentucky Law Summary',
         'variations': {},
         'editions': {'Ky. L. Summ.': (date(1966, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ky'},],

    'La.':
        [{'name': 'Louisiana Reports',
         'variations': {},
         'editions': {'La.': (date(1830, 1, 1), date(1972, 12, 31))}, # Has a gap from 1841 to 1901
         'mlz_jurisdiction': 'us;la'},],
    'Mart.':
        [{'name': 'Louisiana Reports, Martin',
          'variations': {},
          'editions': {'Mart.': (date(1809, 1, 1), date(1830, 12, 31))},
          'mlz_jurisdiction': 'us;la'},
         {'name': 'North Carolina Reports, Martin',
          'variations': {},
          'editions': {'Mart.': (date(1778, 1, 1), date(1797, 12, 31))},
          'mlz_jurisdiction': 'us;nc'},],
    'Rob.':
        [{'name': 'Louisiana Reports, Robinson',
          'variations': {},
          'editions': {'Rob.': (date(1841, 1, 1), date(1846, 12, 31))},
          'mlz_jurisdiction': 'us;la'},
         {'name': 'Virginia Reports, Robinson',
          'variations': {},
          'editions': {'Rob.': (date(1842, 1, 1), date(1844, 12, 31))},
          'mlz_jurisdiction': 'us;va'},],
    'La. Ann.':
        [{'name': 'Louisiana Annual Reports',
         'variations': {},
         'editions': {'La. Ann.': (date(1846, 1, 1), date(1900, 12, 31))},
         'mlz_jurisdiction': 'us;la'},],
    'McGl.':
        [{'name': 'Louisiana Court of Appeals Reports, McGloin',
         'variations': {},
         'editions': {'McGl.': (date(1881, 1, 1), date(1884, 12, 31))},
         'mlz_jurisdiction': 'us;la'},],
    'Gunby':
        [{'name': 'Louisiana Court of Appeals Reports, Gunby',
         'variations': {},
         'editions': {'Gunby': (date(1885, 1, 1), date(1885, 12, 31))},
         'mlz_jurisdiction': 'us;la'},],
    'Teiss.':
        [{'name': 'Louisiana Court of Appeals Reports, Teisser',
         'variations': {},
         'editions': {'Teiss.': (date(1903, 1, 1), date(1917, 12, 31))},
         'mlz_jurisdiction': 'us;la'},],
    'Pelt.':
        [{'name': 'Peltier\'s Opinions, Parish at Orleans',
         'variations': {},
         'editions': {'Pelt.': (date(1917, 1, 1), date(1924, 12, 31))},
         'mlz_jurisdiction': 'us;la'},],
    'La. App.':
        [{'name': 'Louisiana Court of Appeals Reports',
         'variations': {},
         'editions': {'La. App.': (date(1924, 1, 1), date(1932, 12, 31))},
         'mlz_jurisdiction': 'us;la'},],

    'Me.':
        [{'name': 'Maine Reports',
         'variations': {},
         'editions': {'Me.': (date(1820, 1, 1), date(1965, 12, 31))},
         'mlz_jurisdiction': 'us;me'},],

    'H. & McH.':
        [{'name': 'Maryland Reports, Harris and McHenry',
         'variations': {},
         'editions': {'H. & McH.': (date(1770, 1, 1), date(1799, 12, 31))}, # Gap from 1774 to 1780
         'mlz_jurisdiction': 'us;md'},],
    'H. & J.':
        [{'name': 'Maryland Reports, Harris and Johnson',
         'variations': {},
         'editions': {'H. & J.': (date(1800, 1, 1), date(1826, 12, 31))},
         'mlz_jurisdiction': 'us;md'},],
    'H. & G.':
        [{'name': 'Maryland Reports, Harris and Gill',
         'variations': {},
         'editions': {'H. & G.': (date(1826, 1, 1), date(1829, 12, 31))},
         'mlz_jurisdiction': 'us;md'},],
    'G. & J.':
        [{'name': 'Maryland Reports, Gill & Johnson',
         'variations': {},
         'editions': {'G. & J.': (date(1829, 1, 1), date(1842, 12, 31))},
         'mlz_jurisdiction': 'us;md'},],
    'Gill':
        [{'name': 'Maryland Reports, Gill',
         'variations': {},
         'editions': {'Gill': (date(1843, 1, 1), date(1851, 12, 31))},
         'mlz_jurisdiction': 'us;md'},],
    'Md.':
        [{'name': 'Maryland Reports',
         'variations': {},
         'editions': {'Md.': (date(1851, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;md'},],
    'Md. App.':
        [{'name': 'Maryland Appellate Reports',
         'variations': {},
         'editions': {'Md. App.': (date(1967, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;md'},],

    'Will.':
        [{'name': 'Massachusetts Reports, Williams',
         'variations': {},
         'editions': {'Will.': (date(1804, 1, 1), date(1805, 12, 31))},
         'mlz_jurisdiction': 'us;ma'},],
    'Tyng':
        [{'name': 'Massachusetts Reports, Tyng',
         'variations': {},
         'editions': {'Tyng': (date(1806, 1, 1), date(1822, 12, 31))},
         'mlz_jurisdiction': 'us;ma'},],
    'Pick.':
        [{'name': 'Massachusetts Reports, Pickering',
         'variations': {},
         'editions': {'Pick.': (date(1822, 1, 1), date(1839, 12, 31))},
         'mlz_jurisdiction': 'us;ma'},],
    # For additional MA reporter, see 'Met.' key
    'Cush.':
        [{'name': 'Massachusetts Reports, Cushing',
         'variations': {},
         'editions': {'Cush.': (date(1848, 1, 1), date(1853, 12, 31))},
         'mlz_jurisdiction': 'us;ma'},],
    'Gray':
        [{'name': 'Massachusetts Reports, Gray',
         'variations': {},
         'editions': {'Gray': (date(1854, 1, 1), date(1860, 12, 31))},
         'mlz_jurisdiction': 'us;ma'},],
    'Allen':
        [{'name': 'Massachusetts Reports, Allen',
         'variations': {},
         'editions': {'Allen': (date(1861, 1, 1), date(1867, 12, 31))},
         'mlz_jurisdiction': 'us;ma'},],
    'Mass.':
        [{'name': 'Massachusetts Reports',
         'variations': {},
         'editions': {'Mass.': (date(1867, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ma'},],
    'Mass. App. Ct.':
        [{'name': 'Massachusetts Appeals Court Reports',
         'variations': {},
         'editions': {'Mass. App. Ct.': (date(1972, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ma'},],
    'Mass. Supp.':
        [{'name': 'Massachusetts Reports Supplement',
         'variations': {},
         'editions': {'Mass. Supp.': (date(1980, 1, 1), date(1983, 12, 31))},
         'mlz_jurisdiction': 'us;ma'},],
    'Mass. App. Dec.':
        [{'name': 'Massachusetts Appellate Decisions',
         'variations': {},
         'editions': {'Mass. App. Dec.': (date(1941, 1, 1), date(1977, 12, 31))},
         'mlz_jurisdiction': 'us;ma'},],
    'Mass. App. Div.':
        [{'name': 'Reports of Massachusetts Appellate Division',
         'variations': {},
         'editions': {'Mass. App. Div.': (date(1936, 1, 1), date.today())}, # Gap from 1950 to 1980
         'mlz_jurisdiction': 'us;ma'},],

    'Blume Sup. Ct. Trans.':
        [{'name': 'Blume, Supreme Court Transactions',
         'variations': {},
         'editions': {'Blume Sup. Ct. Trans.': (date(1805, 1, 1), date(1836, 12, 31))},
         'mlz_jurisdiction': 'us;mi'},],
    'Blume Unrep. Op.':
        [{'name': 'Blume, Unreported Opinions',
         'variations': {},
         'editions': {'Blume Unrep. Op.': (date(1836, 1, 1), date(1843, 12, 31))},
         'mlz_jurisdiction': 'us;mi'},],
    'Doug.':
        [{'name': 'Michigan Reports, Douglass',
         'variations': {},
         'editions': {'Doug.': (date(1843, 1, 1), date(1847, 12, 31))},
         'mlz_jurisdiction': 'us;mi'},],
    'Mich.':
        [{'name': 'Michigan Reports',
         'variations': {},
         'editions': {'Mich.': (date(1847, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;mi'},],
    'Mich. App.':
        [{'name': 'Michigan Appeals Reports',
         'variations': {},
         'editions': {'Mich. App.': (date(1965, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;mi'},],
    'Mich. Ct. Cl.':
        [{'name': 'Michigan Court of Claims Reports',
         'variations': {},
         'editions': {'Mich. Ct. Cl.': (date(1938, 1, 1), date(1942, 12, 31))},
         'mlz_jurisdiction': 'us;mi'},],

    'Minn.':
        [{'name': 'Minnesota Reports',
         'variations': {},
         'editions': {'Minn.': (date(1851, 1, 1), date(1977, 12, 31))},
         'mlz_jurisdiction': 'us;mn'},],

    'Walker':
        [{'name': 'Mississippi Reports, Walker',
         'variations': {},
         'editions': {'Walker': (date(1818, 1, 1), date(1832, 12, 31))},
         'mlz_jurisdiction': 'us;ms'},],
    'Howard':
        [{'name': 'Mississippi Reports, Howard',
         'variations': {},
         'editions': {'Howard': (date(1834, 1, 1), date(1843, 12, 31))},
         'mlz_jurisdiction': 'us;ms'},],
    'S. & M.':
        [{'name': 'Mississippi Reports, Smedes and Marshall',
         'variations': {},
         'editions': {'S. & M.': (date(1843, 1, 1), date(1850, 12, 31))},
         'mlz_jurisdiction': 'us;ms'},],
    'Miss.':
        [{'name': 'Mississippi Reports',
         'variations': {},
         'editions': {'Miss.': (date(1851, 1, 1), date(1966, 12, 31))},
         'mlz_jurisdiction': 'us;ms'},],

    'Mo.':
        [{'name': 'Missouri Reports',
         'variations': {},
         'editions': {'Mo.': (date(1821, 1, 1), date(1956, 12, 31))},
         'mlz_jurisdiction': 'us;mo'},],
    'Mo. App.':
        [{'name': 'Missouri Appeals Reports',
         'variations': {},
         'editions': {'Mo. App.': (date(1876, 1, 1), date(1954, 12, 31))},
         'mlz_jurisdiction': 'us;mo'},],

    'Mont.':
        [{'name': 'Montana Reports',
         'variations': {},
         'editions': {'Mont.': (date(1868, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;mt'},],
    'State Rptr.':
        [{'name': 'State Reporter', # Who named this?
         'variations': {},
         'editions': {'State Rptr.': (date(1945, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;mt'},],

    'Neb.':
        [{'name': 'Nebraska Reports',
         'variations': {},
         'editions': {'Neb.': (date(1860, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ne'},],
    'Neb. Ct. App.':
        [{'name': 'Nebraska Court of Appeals Reports',
         'variations': {'Neb. App.': 'Neb. Ct. App.'},
         'editions': {'Neb. Ct. App.': (date(1922, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ne'},],

    'Nev.':
        [{'name': 'Nevada Reports',
         'variations': {},
         'editions': {'Nev.': (date(1865, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;nv'},],
    'Nev. Adv. Op. No.':
        [{'name': 'Nevada Advanced Opinion',
         'variations': {},
         # When did this format begin?
         'editions': {'Nev. Adv. Op. No.': (date(1750, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;nv'},],

    'N.H.':
        [{'name': 'New Hampshire Reports',
         'variations': {},
         'editions': {'N.H.': (date(1816, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;nh'},],

    'N.J.':
        [{'name': 'New Jersey Reports',
         'variations': {},
         'editions': {'N.J.': (date(1948, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;nj'},],
    'N.J.L.':
        [{'name': 'New Jersey Law Reports',
         'variations': {},
         'editions': {'N.J.L.': (date(1790, 1, 1), date(1948, 12, 31))},
         'mlz_jurisdiction': 'us;nj'},],
    'N.J. Eq.':
        [{'name': 'New Jersey Equity Reports',
         'variations': {},
         'editions': {'N.J. Eq.': (date(1830, 1, 1), date(1948, 12, 31))},
         'mlz_jurisdiction': 'us;nj'},],
    'N.J. Misc.':
        [{'name': 'New Jersey Miscellaneous Reports',
         'variations': {},
         'editions': {'N.J. Misc.': (date(1923, 1, 1), date(1949, 12, 31))},
         'mlz_jurisdiction': 'us;nj'},],
    'N.J. Super.':
        [{'name': 'New Jersey Superior Court Reports',
         'variations': {},
         'editions': {'N.J. Super.': (date(1948, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;nj'},],
    'N.J. Tax':
        [{'name': 'New Jersey Tax Court',
         'variations': {},
         'editions': {'N.J. Tax.': (date(1979, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;nj'},],
    'N.J. Admin.':
        [{'name': 'New Jersey Administrative Reports',
         'variations': {},
         # Dates need research
         'editions': {'N.J. Admin.': (date(1982, 1, 1), date.today()),
                      'N.J. Admin. 2d': (date(1982, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;nj'},],

    'Gild.':
        [{'name': 'Gildersleeve Reports',
         'variations': {},
         'editions': {'Gild.': (date(1883, 1, 1), date(1889, 12, 31))},
         'mlz_jurisdiction': 'us;nm'},],
    'N.M.':
        [{'name': 'New Mexico Reports',
         'variations': {},
         'editions': {'N.M.': (date(1890, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;nm'},],

    'N.Y.':
        [{'name': 'New York Reports',
         'variations': {'N.Y. 3d': 'N.Y.3d',
                        'NY 3d': 'N.Y.3d',
                        'N.Y. 2d': 'N.Y.2d',
                        'NY 2d': 'N.Y.2d',
                        'N. Y.': 'N.Y.', },
         'editions': {'N.Y.': (date(1847, 1, 1), date(1956, 12, 31)),
                      'N.Y.2d': (date(1956, 1, 1), date(2004, 1, 1)),
                      'N.Y.3d': (date(2004, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ny'},],
    'N.Y.S.':
        [{'name': 'New York Supplement',
         'variations': {'New York Supp.': 'N.Y.S.',
                        'NYS': 'N.Y.S.',
                        'NYS 2d': 'N.Y.S.2d',
                        'N.Y.S. 3d': 'N.Y.S.3d',
                        'NYS 3d': 'N.Y.S.3d',
                        'N.Y.S. 2d': 'N.Y.S.2d', },
         'editions': {'N.Y.S.': (date(1888, 1, 1), date(1937, 12, 31)),
                      'N.Y.S.2d': (date(1938, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ny'},],
    'Lock. Rev. Cas.':
        [{'name': 'Lockwood\'s Reversed Cases',
         'variations': {},
         'editions': {'Lock. Rev. Cas.': (date(1799, 1, 1), date(1847, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Denio':
        [{'name': 'Denio\'s Reports',
         'variations': {},
         'editions': {'Denio': (date(1845, 1, 1), date(1848, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Hill & Den.':
        [{'name': 'Hill and Denio Supplement (Lalor)',
         'variations': {},
         'editions': {'Hill & Den.': (date(1842, 1, 1), date(1844, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Hill':
        [{'name': 'Hill\'s Reports',
          'variations': {},
          'editions': {'Hill': (date(1841, 1, 1), date(1844, 12, 31))},
          'mlz_jurisdiction': 'us;ny'},
         {'name': 'South Carolina Reports, Hill',
          'variations': {},
          'editions': {'Hill': (date(1833, 1, 1), date(1837, 12, 31))},
          'mlz_jurisdiction': 'us;sc'},],
    'Edm. Sel. Cas.':
        [{'name': 'Edmond\'s Select Cases',
         'variations': {},
         'editions': {'Edm. Sel. Cas.': (date(1834, 1, 1), date(1853, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Yates Sel. Cas.':
        [{'name': 'Yates\' Select Cases',
         'variations': {},
         'editions': {'Yates Sel. Cas.': (date(1809, 1, 1), date(1809, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Ant. N.P. Cas.':
        [{'name': 'Anthon\'s Nisi Prius Cases',
         'variations': {},
         'editions': {'Ant. N.P. Cas.': (date(1807, 1, 1), date(1851, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Wend.':
        [{'name': 'Wendell\'s Reports',
         'variations': {},
         'editions': {'Wend.': (date(1828, 1, 1), date(1841, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Cow.':
        [{'name': 'Cowen\'s Reports',
         'variations': {},
         'editions': {'Cow.': (date(1823, 1, 1), date(1829, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Johns.':
        [{'name': 'Johnson\'s Reports',
         'variations': {},
         'editions': {'Johns.': (date(1806, 1, 1), date(1823, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Cai. R.':
        [{'name': 'Caines\' Reports',
         'variations': {},
         'editions': {'Cai. R.': (date(1803, 1, 1), date(1805, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Cai. Cas.':
        [{'name': 'Caines\' Cases',
         'variations': {},
         'editions': {'Cai. Cas.': (date(1796, 1, 1), date(1805, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Cole. & Cai. Cas.':
        [{'name': 'Coleman & Caines\' Cases',
         'variations': {},
         'editions': {'Cole. & Cai. Cas.': (date(1794, 1, 1), date(1805, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Johns. Cas.':
        [{'name': 'Johnson\'s Cases',
         'variations': {},
         'editions': {'Johns. Cas.': (date(1799, 1, 1), date(1803, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Cole. Cas.':
        [{'name': 'Coleman\'s Cases',
         'variations': {},
         'editions': {'Cole. Cas.': (date(1791, 1, 1), date(1800, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Edw. Ch.':
        [{'name': 'Edwards\' Chancery Reports',
         'variations': {},
         'editions': {'Edw. Ch.': (date(1831, 1, 1), date(1850, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Barb. Ch.':
        [{'name': 'Barbour\'s Chancery Reports',
         'variations': {},
         'editions': {'Barb. Ch.': (date(1845, 1, 1), date(1848, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Sand. Ch.':
        [{'name': 'Sandford\'s Chancery Reports',
         'variations': {},
         'editions': {'Sand. Ch.': (date(1843, 1, 1), date(1847, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Sarat. Ch. Sent.':
        [{'name': 'Saratoga Chancery Sentinel',
         'variations': {},
         'editions': {'Sarat. Ch. Sent.': (date(1841, 1, 1), date(1847, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Paige Ch.':
        [{'name': 'Paige\'s Chancery Reports',
         'variations': {},
         'editions': {'Paige Ch.': (date(1828, 1, 1), date(1845, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Cl. Ch.':
        [{'name': 'Clarke\'s Chancery Reports',
         'variations': {},
         'editions': {'Cl. Ch.': (date(1839, 1, 1), date(1841, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Hoff. Ch.':
        [{'name': 'Hoffman\'s Chancery Reports',
         'variations': {},
         'editions': {'Hoff. Ch.': (date(1838, 1, 1), date(1840, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Hopk. Ch.':
        [{'name': 'Hopkins\' Chancery Reports',
         'variations': {},
         'editions': {'Hopk. Ch.': (date(1823, 1, 1), date(1826, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Lans. Ch.':
        [{'name': 'Lansing\'s Chancery Reports',
         'variations': {},
         'editions': {'Lans. Ch.': (date(1824, 1, 1), date(1826, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Johns. Ch.':
        [{'name': 'Johnsons\' Chancery Reports',
         'variations': {},
         'editions': {'Johns. Ch.': (date(1814, 1, 1), date(1823, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'N.Y. Ch. Ann.':
        [{'name': 'New York Chancery Reports Annotated',
         'variations': {},
         'editions': {'N.Y. Ch. Ann.': (date(1814, 1, 1), date(1847, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'A.D.':
        [{'name': 'New York Supreme Court Appellate Division Reports',
         'variations': {'Ap.': 'A.D.',
                        'App.Div.': 'A.D.',
                        'App.Div.(N.Y.)': 'A.D.',
                        'N.Y.App.Dec.': 'A.D.',
                        'N.Y.App.Div.': 'A.D.',
                        'Ap.2d.': 'A.D.',
                        'App.Div.2d.': 'A.D.',
                        'A.D. 3d': 'A.D.3d',
                        'AD 3d': 'A.D.3d',
                        'A.D. 2d': 'A.D.2d',
                        'AD 2d': 'A.D.2d', },
         'editions': {'A.D.': (date(1896, 1, 1), date(1955, 12, 31)),
                      # Dates are fuzzy here and thus have overlap.
                      # Best guess is based on: http://www.antiqbook.com/boox/law/57231.shtml
                      'A.D.2d': (date(1955, 1, 1), date(2004, 12, 31)),
                      'A.D.3d': (date(2003, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ny'},],
    'N.Y. Sup. Ct.':
        [{'name': 'Supreme Court Reports',
         'variations': {},
         'editions': {'N.Y. Sup. Ct.': (date(1873, 1, 1), date(1896, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Lans.':
        [{'name': 'Lansing\'s Reports',
         'variations': {},
         'editions': {'Lans.': (date(1869, 1, 1), date(1873, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Barb.':
        [{'name': 'Barbour\'s Supreme Court Reports',
         'variations': {},
         'editions': {'Barb.': (date(1847, 1, 1), date(1877, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Misc.':
        [{'name': 'New York Miscellaneous Reports',
         'variations': {'Misc.3d': 'Misc. 3d',
                        'Misc 3d': 'Misc. 3d',
                        'Misc.2d': 'Misc. 2d',
                        'Misc 2d': 'Misc. 2d', },
         'editions': {'Misc.': (date(1892, 1, 1), date(1955, 12, 31)),
                      'Misc. 2d': (date(1955, 1, 1), date(2004, 12, 31)),
                      # http://www.antiqbook.com/boox/law/59388.shtml
                      'Misc. 3d': (date(2004, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ny'},],
    'Abb. N. Cas.':
        [{'name': 'Abbott\'s New Cases',
         'variations': {},
         'editions': {'Abb. N. Cas.': (date(1876, 1, 1), date(1894, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'Abb. Pr.':
        [{'name': 'Abbott\'s Practice Reports',
         'variations': {},
         'editions': {'Abb. Pr.': (date(1854, 1, 1), date(1875, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'How. Pr.':
        [{'name': 'Howard\'s Practice Reports',
         'variations': {},
         'editions': {'How. Pr.': (date(1844, 1, 1), date(1886, 12, 31))},
         'mlz_jurisdiction': 'us;ny'},],
    'NY Slip Op':
        [{'name': 'New York Slip Opinion',
         'variations': {},
         # When did this format come into usage?
         'editions': {'NY Slip Op': (date(1750, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;ny'},],

    # For additional reporter, see 'Mart.' key.
    'Tay.':
        [{'name': 'North Carolina Reports, Taylor',
         'variations': {},
         'editions': {'Tay.': (date(1798, 1, 1), date(1802, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Cam. & Nor.':
        [{'name': 'North Carolina Reports, Conference by Cameron & Norwood',
         'variations': {},
         'editions': {'Cam. & Nor.': (date(1800, 1, 1), date(1804, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Hayw.':
        [{'name': 'North Carolina Reports, Haywood',
          'variations': {},
          'editions': {'Hayw.': (date(1789, 1, 1), date(1806, 12, 31))},
          'mlz_jurisdiction': 'us;nc'},
         {'name': 'Tennessee Reports, Haywood',
          'variations': {},
          'editions': {'Hayw.': (date(1816, 1, 1), date(1818, 12, 31))},
          'mlz_jurisdiction': 'us;tn'},],
    'Car. L. Rep.':
        [{'name': 'Carolina Law Repository',
         'variations': {},
         'editions': {'Car. L. Rep.': (date(1811, 1, 1), date(1816, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Taylor':
        [{'name': 'Taylor\'s North Carolina Term Reports',
         'variations': {},
         'editions': {'Taylor': (date(1816, 1, 1), date(1818, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Mur.':
        [{'name': 'North Carolina Reports, Murphey',
         'variations': {},
         'editions': {'Mur.': (date(1804, 1, 1), date(1819, 12, 31))}, # Gap from 1813 to 1818
         'mlz_jurisdiction': 'us;nc'},],
    'Hawks':
        [{'name': 'North Carolina Reports, Hawks',
         'variations': {},
         'editions': {'Hawks': (date(1820, 1, 1), date(1826, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Dev.':
        [{'name': 'North Carolina Reports, Devereux\'s Law',
         'variations': {},
         'editions': {'Dev.': (date(1826, 1, 1), date(1834, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Dev. Eq.':
        [{'name': 'North Carolina Reports, Devereux\'s Equity',
         'variations': {},
         'editions': {'Dev. Eq.': (date(1826, 1, 1), date(1834, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Dev. & Bat.':
        [{'name': 'North Carolina Reports, Devereux & Battle\'s Law',
         'variations': {},
         'editions': {'Dev. & Bat.': (date(1834, 1, 1), date(1839, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Dev. & Bat. Eq.':
        [{'name': 'North Carolina Reports, Devereux & Battle\'s Equity',
         'variations': {},
         'editions': {'Dev. & Bat. Eq.': (date(1834, 1, 1), date(1839, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Ired.':
        [{'name': 'North Carolina Reports, Iredell\'s Law',
         'variations': {},
         'editions': {'Ired.': (date(1840, 1, 1), date(1852, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Ired. Eq.':
        [{'name': 'North Carolina Reports, Iredell\'s Equity',
         'variations': {},
         'editions': {'Ired. Eq.': (date(1840, 1, 1), date(1852, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Busb.':
        [{'name': 'North Carolina Reports, Busbee\'s Law',
         'variations': {},
         'editions': {'Busb.': (date(1852, 1, 1), date(1853, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Busb. Eq.':
        [{'name': 'North Carolina Reports, Busbee\'s Equity',
         'variations': {},
         'editions': {'Busb. Eq.': (date(1852, 1, 1), date(1853, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Jones':
        [{'name': 'North Carolina Reports, Jones\' Law',
         'variations': {},
         'editions': {'Jones': (date(1853, 1, 1), date(1862, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Jones Eq.':
        [{'name': 'North Carolina Reports, Jones\' Equity',
         'variations': {},
         'editions': {'Jones Eq.': (date(1853, 1, 1), date(1863, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Win.':
        [{'name': 'North Carolina Reports, Winston',
         'variations': {},
         'editions': {'Win.': (date(1863, 1, 1), date(1864, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Phil. Law':
        [{'name': 'North Carolina Reports, Philips\' Law',
         'variations': {},
         'editions': {'Phil. Law': (date(1866, 1, 1), date(1868, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'Phil. Eq.':
        [{'name': 'North Carolina Reports, Philips\' Equity',
         'variations': {},
         'editions': {'Phil. Eq.': (date(1866, 1, 1), date(1868, 12, 31))},
         'mlz_jurisdiction': 'us;nc'},],
    'N.C.':
        [{'name': 'North Carolina Reports',
         'variations': {},
         'editions': {'N.C.': (date(1868, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;nc'},],
    'N.C. App.':
        [{'name': '',
         'variations': {},
         'editions': {'N.C. App.': (date(1968, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;nc'},],

    'N.D.':
        [{'name': 'North Dakota Reports',
         'variations': {},
         'editions': {'N.D.': (date(1890, 1, 1), date(1953, 12, 31))},
         'mlz_jurisdiction': 'us;nd'},],
    'Dakota':
        [{'name': 'Dakota Reports',
         'variations': {},
         'editions': {'Dakota': (date(1867, 1, 1), date(1889, 12, 31))},
         'mlz_jurisdiction': 'us;nd'},],

    'Ohio':
        [{'name': 'Ohio Reports',
         'variations': {},
         'editions': {'Ohio': (date(1821, 1, 1), date(1851, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio St.':
        [{'name': 'Ohio State Reports',
         'variations': {'O.S.': 'Ohio St.',
                        'Oh.St.': 'Ohio St.',
                        'O.S.2d': 'Ohio St. 2d',
                        'Ohio St.2d': 'Ohio St. 2d',
                        'O.S.3d': 'Ohio St. 3d',
                        'Ohio St.3d': 'Ohio St. 3d', },
         'editions': {'Ohio St.': (date(1840, 1, 1), date(1964, 12, 31)),
                      'Ohio St. 2d': (date(1965, 1, 1), date(1991, 12, 31)),
                      'Ohio St. 3d': (date(1991, 1, 1), date.today()), },
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio App.':
        [{'name': 'Ohio Appellate Reports',
         'variations': {},
         # Needs research
         'editions': {'Ohio App.': (date(1913, 1, 1), date.today()),
                      'Ohio App. 2d': (date(1913, 1, 1), date.today()),
                      'Ohio App. 3d': (date(1913, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio Misc.':
        [{'name': 'Ohio Miscellaneous',
         'variations': {},
         # Needs research
         'editions': {'Ohio Misc.': (date(1962, 1, 1), date.today()),
                      'Ohio Misc. 2d': (date(1962, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio B.':
        [{'name': 'Ohio Bar Reports',
         'variations': {},
         'editions': {'Ohio B.': (date(1982, 1, 1), date(1987, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio Op.':
        [{'name': 'Ohio Opinions',
         'variations': {},
         'editions': {'Ohio Op.': (date(1934, 1, 1), date(1982, 12, 31)),
                      'Ohio Op. 2d': (date(1934, 1, 1), date(1982, 12, 31)),
                      'Ohio Op. 3d': (date(1934, 1, 1), date(1982, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio Law. Abs.':
        [{'name': 'Ohio Law Abstracts',
         'variations': {},
         'editions': {'Ohio Law. Abs.': (date(1922, 1, 1), date(1964, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio N.P.':
        [{'name': 'Ohio Nisi Prius Reports',
         'variations': {},
         'editions': {'Ohio N.P.': (date(1894, 1, 1), date(1934, 12, 31)),
                      'Ohio N.P. (n.s.)': (date(1894, 1, 1), date(1934, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio Dec.':
        [{'name': 'Ohio Decisions',
         'variations': {},
         'editions': {'Ohio Dec.': (date(1894, 1, 1), date(1920, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio Dec. Reprint':
        [{'name': 'Ohio Decisions, Reprint',
         'variations': {},
         'editions': {'Ohio Dec. Reprint': (date(1840, 1, 1), date(1873, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio Cir. Dec.':
        [{'name': 'Ohio Circuit Decisions',
         'variations': {},
         'editions': {'Ohio Cir. Dec.': (date(1885, 1, 1), date(1901, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio C.C. Dec.':
        [{'name': 'Ohio Circuit Court Decisions',
         'variations': {},
         'editions': {'Ohio C.C. Dec.': (date(1901, 1, 1), date(1923, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio C.C.':
        [{'name': 'Ohio Circuit Court Reports',
         'variations': {},
         'editions': {'Ohio C.C.': (date(1885, 1, 1), date(1901, 12, 31)),
                      'Ohio C.C. (n.s.)': (date(1901, 1, 1), date(1922, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],
    'Ohio App. Unrep.':
        [{'name': 'Unreported Ohio Appellate Cases (Anderson)',
         'variations': {},
         'editions': {'Ohio App. Unrep.': (date(1990, 1, 1), date(1990, 12, 31))},
         'mlz_jurisdiction': 'us;oh'},],

    'Okla.':
        [{'name': 'Oklahoma Reports',
         'variations': {},
         'editions': {'Okla': (date(1890, 1, 1), date(1953, 12, 31))},
         'mlz_jurisdiction': 'us;ok'},],
    'Indian Terr.':
        [{'name': 'Indian Territory Reports',
         'variations': {},
         'editions': {'Indian Terr.': (date(1896, 1, 1), date(1907, 12, 31))},
         'mlz_jurisdiction': 'us;ok'},],
    'Okla. Crim.':
        [{'name': 'Oklahoma Criminal Reports',
         'variations': {},
         'editions': {'Okla. Crim.': (date(1908, 1, 1), date(1953, 12, 31))},
         'mlz_jurisdiction': ''},],

    'Or.':
        [{'name': 'Oregon Reports',
         'variations': {},
         'editions': {'Or.': (date(1853, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;or'},],
    'Or. App.':
        [{'name': 'Oregon Reports, Court of Appeals',
         'variations': {},
         'editions': {'Or. App.': (date(1969, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;or'},],
    'Or. Tax':
        [{'name': 'Oregon Tax Reports',
         'variations': {},
         'editions': {'Or. Tax': (date(1962, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;or'},],

    'Monag.':
        [{'name': 'Pennsylvania State Reports, Monaghan',
         'variations': {},
         'editions': {'Monag.': (date(1888, 1, 1), date(1890, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Sadler':
        [{'name': 'Pennsylvania State Reports, Sadler',
         'variations': {},
         'editions': {'Sadler': (date(1885, 1, 1), date(1888, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Walk.':
        [{'name': 'Pennsylvania State Reports, Walker',
         'variations': {},
         'editions': {'Walk': (date(1855, 1, 1), date(1885, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Pennyp.':
        [{'name': 'Pennsylvania State Reports, Pennypacker',
         'variations': {},
         'editions': {'Pennyp.': (date(1881, 1, 1), date(1884, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Grant':
        [{'name': 'Pennsylvania State Reports, Grant',
         'variations': {},
         'editions': {'Grant': (date(1814, 1, 1), date(1863, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Watts & Serg.':
        [{'name': 'Pennsylvania State Reports, Watts & Sergeant',
         'variations': {},
         'editions': {'Watts & Serg.': (date(1841, 1, 1), date(1845, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Whart.':
        [{'name': 'Pennsylvania State Reports, Wharton',
         'variations': {},
         'editions': {'Whart.': (date(1835, 1, 1), date(1841, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Watts':
        [{'name': 'Pennsylvania State Reports, Watts',
         'variations': {},
         'editions': {'Watts': (date(1832, 1, 1), date(1840, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Rawle':
        [{'name': 'Pennsylvania State Reports, Rawle',
         'variations': {},
         'editions': {'Rawle': (date(1828, 1, 1), date(1835, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Pen. & W.':
        [{'name': 'Pennsylvania State Reports, Penrose and Watts',
         'variations': {},
         'editions': {'Pen. & W.': (date(1829, 1, 1), date(1832, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Serg. & Rawle':
        [{'name': 'Pennsylvania State Reports, Sergeant and Rawle',
         'variations': {},
         'editions': {'Serg. & Rawle': (date(1814, 1, 1), date(1828, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Binn.':
        [{'name': 'Pennsylvania State Reports, Binney',
         'variations': {},
         'editions': {'Binn': (date(1799, 1, 1), date(1814, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Yeates':
        [{'name': 'Pennsylvania State Reports, Yeates',
         'variations': {},
         'editions': {'Yeates': (date(1791, 1, 1), date(1808, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    # See 'Dall.' key for additional reporter.

    'Pa.':
        [{'name': 'Pennsylvania State Reports',
         'variations': {},
         'editions': {'Pa.': (date(1845, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;pa'},],
    'Pa. Super.':
        [{'name': 'Pennsylvania Superior Court Reports',
         'variations': {'Pa. Superior Ct.': 'Pa. Super.', },
         'editions': {'Pa. Super.': (date(1895, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;pa'},],
    'Pa. Commw.':
        [{'name': 'Pennsylvania Commonwealth Court',
         'variations': {'Pa. Commonwealth Ct.': 'Pa. Commw.', },
         'editions': {'Pa. Commw.': (date(1970, 1, 1), date(1994, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Pa. D. & C.':
        [{'name': 'Pennsylvania District and County Reports',
         'variations': {},
         'editions': {'Pa. D. & C.': (date(1921, 1, 1), date.today()),
                      'Pa. D. & C.2d': (date(1921, 1, 1), date.today()),
                      'Pa. D. & C.3d': (date(1921, 1, 1), date.today()),
                      'Pa. D. & C.4th': (date(1921, 1, 1), date.today()), },
         'mlz_jurisdiction': 'us;pa'},],
    'Pa. D.':
        [{'name': 'Pennsylvania District Reports',
         'variations': {},
         'editions': {'Pa. D.': (date(1892, 1, 1), date(1921, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],
    'Pa. C.':
        [{'name': 'Pennsylvania County Court Reports',
         'variations': {},
         'editions': {'Pa. C.': (date(1870, 1, 1), date(1921, 12, 31))},
         'mlz_jurisdiction': 'us;pa'},],

    'R.I.':
        [{'name': 'Rhode Island Reports',
         'variations': {},
         'editions': {'R.I.': (date(1828, 1, 1), date(1980, 12, 31))},
         'mlz_jurisdiction': 'us;ri'},],

    'S.C.':
        [{'name': 'South Carolina Reports',
         'variations': {},
         'editions': {'S.C.': (date(1868, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;sc'},],
    'Rich.':
        [{'name': 'South Carolina Reports, Richardson',
         'variations': {},
         'editions': {'Rich.': (date(1846, 1, 1), date(1868, 12, 31))}, # Gap from 1846 to 1850
         'mlz_jurisdiction': 'us;sc'},],
    'Strob.':
        [{'name': 'South Carolina Reports, Strobhart',
         'variations': {},
         'editions': {'Strob.': (date(1846, 1, 1), date(1850, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Speers':
        [{'name': 'South Carolina Reports, Speers',
         'variations': {},
         'editions': {'Speers': (date(1842, 1, 1), date(1844, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'McMul.':
        [{'name': 'South Carolina Reports, McMullen',
         'variations': {},
         'editions': {'McMul.': (date(1840, 1, 1), date(1842, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Chev.':
        [{'name': 'South Carolina Reports, Cheves',
         'variations': {},
         'editions': {'Chev.': (date(1839, 1, 1), date(1840, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Rice':
        [{'name': 'South Carolina Reports, Rice',
         'variations': {},
         'editions': {'Rice': (date(1838, 1, 1), date(1839, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Dud.':
        [{'name': 'South Carolina Reports, Dudley',
         'variations': {},
         'editions': {'Dud.': (date(1837, 1, 1), date(1838, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Ril.':
        [{'name': 'South Carolina Reports, Riley',
         'variations': {},
         'editions': {'Ril.': (date(1836, 1, 1), date(1837, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    # For additional SC reporter, see 'Hill'
    'Bail.':
        [{'name': 'South Carolina Reports, Bailey',
         'variations': {},
         'editions': {'Bail.': (date(1828, 1, 1), date(1832, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Harp.':
        [{'name': 'South Carolina Reports, Harper',
         'variations': {},
         'editions': {'Harp.': (date(1823, 1, 1), date(1831, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'McCord':
        [{'name': 'South Carolina Reports, McCord',
         'variations': {},
         'editions': {'McCord': (date(1821, 1, 1), date(1828, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Nott & McC.':
        [{'name': 'South Carolina Reports, Nott and McCord',
         'variations': {},
         'editions': {'Nott & McC.': (date(1817, 1, 1), date(1820, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Mill':
        [{'name': 'South Carolina Reports, Mill (Constitutional)',
         'variations': {},
         'editions': {'Mill': (date(1817, 1, 1), date(1818, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Tread.':
        [{'name': 'South Carolina Reports, Treadway',
         'variations': {},
         'editions': {'Tread.': (date(1812, 1, 1), date(1816, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Brev.':
        [{'name': 'South Carolina Reports, Brevard',
         'variations': {},
         'editions': {'Brev.': (date(1793, 1, 1), date(1816, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Bay':
        [{'name': 'South Carolina Reports, Bay',
         'variations': {},
         'editions': {'Bay': (date(1783, 1, 1), date(1804, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Rich. Eq.':
        [{'name': 'South Carolina Reports, Richardson\'s Equity',
         'variations': {},
         'editions': {'Rich. Eq.': (date(1844, 1, 1), date(1868, 12, 31))}, # Gap from 1846 to 1850
         'mlz_jurisdiction': 'us;sc'},],
    'Strob. Eq.':
        [{'name': 'South Carolina Reports, Strobhart\'s Equity',
         'variations': {},
         'editions': {'Strob. Eq.': (date(1846, 1, 1), date(1850, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Speers Eq.':
        [{'name': 'South Carolina Reports, Speers\' Equity',
         'variations': {},
         'editions': {'Speers Eq.': (date(1842, 1, 1), date(1844, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'McMul. Eq.':
        [{'name': 'South Carolina Reports, McMullen\'s Equity',
         'variations': {},
         'editions': {'McMul. Eq.': (date(1840, 1, 1), date(1842, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Chev. Eq.':
        [{'name': 'South Carolina Reports, Cheves\' Equity',
         'variations': {},
         'editions': {'Chev. Eq.': (date(1839, 1, 1), date(1840, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Rice Eq.':
        [{'name': 'South Carolina Reports, Rice\'s Equity',
         'variations': {},
         'editions': {'Rice Eq.': (date(1838, 1, 1), date(1839, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Dud. Eq.':
        [{'name': 'South Carolina Reports, Dudley\'s Equity',
         'variations': {},
         'editions': {'Dud. Eq.': (date(1837, 1, 1), date(1838, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Ril. Eq.':
        [{'name': 'South Carolina Reports, Riley\'s Chancery',
         'variations': {},
         'editions': {'Ril. Eq.': (date(1836, 1, 1), date(1837, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Hill Eq.':
        [{'name': 'South Carolina Reports, Hill\'s Chancery',
         'variations': {},
         'editions': {'Hill Eq.': (date(1833, 1, 1), date(1837, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Rich. Cas.':
        [{'name': 'South Carolina Reports, Richardson\'s Cases',
         'variations': {},
         'editions': {'Rich. Cas.': (date(1831, 1, 1), date(1832, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Bail. Eq.':
        [{'name': 'South Carolina Reports, Bailey\'s Equity',
         'variations': {},
         'editions': {'Bail. Eq.': (date(1830, 1, 1), date(1831, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'McCord Eq.':
        [{'name': 'South Carolina Reports, McCord\'s Chancery',
         'variations': {},
         'editions': {'McCord Eq.': (date(1825, 1, 1), date(1827, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Harp. Eq.':
        [{'name': 'South Carolina Reports, Harper\'s Equity',
         'variations': {},
         'editions': {'Harp. Eq.': (date(1824, 1, 1), date(1824, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],
    'Des.':
        [{'name': 'South Carolina Reports, Desaussure\'s Equity',
         'variations': {},
         'editions': {'Des.': (date(1784, 1, 1), date(1817, 12, 31))},
         'mlz_jurisdiction': 'us;sc'},],

    'S.D.':
        [{'name': 'South Dakota Reports',
         'variations': {},
         'editions': {'S.D.': (date(1890, 1, 1), date(1976, 12, 31))},
         'mlz_jurisdiction': 'us;sd'},],

    'Tenn.':
        [{'name': 'Tennessee Reports',
         'variations': {},
         'editions': {'Tenn.': (date(1870, 1, 1), date(1971, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Heisk.':
        [{'name': 'Tennessee Reports, Heiskell',
         'variations': {},
         'editions': {'Heisk.': (date(1870, 1, 1), date(1879, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Cold.':
        [{'name': 'Tennessee Reports, Coldwell',
         'variations': {},
         'editions': {'Cold.': (date(1860, 1, 1), date(1870, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Head':
        [{'name': 'Tennessee Reports, Head',
         'variations': {},
         'editions': {'Head': (date(1858, 1, 1), date(1860, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    # For additional reporter, see 'Sneed'

    'Swan':
        [{'name': 'Tennessee Reports, Swan',
         'variations': {},
         'editions': {'Swan': (date(1851, 1, 1), date(1853, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Hum.':
        [{'name': 'Tennessee Reports, Humphreys',
         'variations': {},
         'editions': {'Hum.': (date(1839, 1, 1), date(1851, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Meigs':
        [{'name': 'Tennessee Reports, Meigs',
         'variations': {},
         'editions': {'Meigs': (date(1838, 1, 1), date(1839, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Yer.':
        [{'name': 'Tennessee Reports, Yerger',
         'variations': {},
         'editions': {'Yer.': (date(1828, 1, 1), date(1837, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Mart. & Yer.':
        [{'name': 'Tennessee Reports, Martin & Yerger',
         'variations': {},
         'editions': {'Mart. & Yer.': (date(1825, 1, 1), date(1828, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Peck':
        [{'name': 'Tennessee Reports, Peck',
         'variations': {},
         'editions': {'Peck': (date(1821, 1, 1), date(1824, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    # For additional TN reporter, see 'Hayw.'
    'Cooke':
        [{'name': 'Tennessee Reports, Cooke',
         'variations': {},
         'editions': {'Cooke': (date(1811, 1, 1), date(1814, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Overt.':
        [{'name': 'Tennessee Reports, Overton',
         'variations': {},
         'editions': {'Overt.': (date(1791, 1, 1), date(1816, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Tenn. App.':
        [{'name': 'Tennessee Appeals Reports',
         'variations': {},
         'editions': {'Tenn. App.': (date(1925, 1, 1), date(1971, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],
    'Tenn. Crim. App.':
        [{'name': 'Tennessee Criminal Appeals Reports',
         'variations': {},
         'editions': {'Tenn. Crim. App.': (date(1967, 1, 1), date(1971, 12, 31))},
         'mlz_jurisdiction': 'us;tn'},],

    'Tex.':
        [{'name': 'Texas Reports',
         'variations': {},
         'editions': {'Tex.': (date(1846, 1, 1), date(1962, 12, 31))},
         'mlz_jurisdiction': 'us;tx'},],
    'Robards':
        [{
            'name': 'Synopses of the Decisions of the Supreme Court of Texas Arising from Restraints by Conscript and Other Military Authorities (Robards)',
            'variations': {},
            'editions': {'Robards': (date(1862, 1, 1), date(1865, 12, 31))},
            'mlz_jurisdiction': 'us;tx'},],
    'Tex. L. Rev.':
        [{'name': 'Texas Law Review',
         'variations': {},
         'editions': {'Tex. L. Rev.': (date(1845, 1, 1), date(1846, 12, 31))},
         'mlz_jurisdiction': 'us;tx'},],
    'Dallam':
        [{'name': 'Digest of the Laws of Texas (Dallam\'s Opinions)',
         'variations': {},
         'editions': {'Dallam': (date(1840, 1, 1), date(1844, 12, 31))},
         'mlz_jurisdiction': 'us;tx'},],
    'Tex. Sup. Ct. J.':
        [{'name': 'Texas Supreme Court Journal',
         'variations': {},
         'editions': {'Tex. Sup. Ct. J.': (date(1957, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;'},],
    'Tex. Crim':
        [{'name': 'Texas Criminal Reports',
         'variations': {},
         'editions': {'Tex. Crim.': (date(1891, 1, 1), date(1962, 12, 31))},
         'mlz_jurisdiction': 'us;tx'},],
    'Tex. Ct. App.':
        [{'name': 'Texas Court of Appeals Reports',
         'variations': {},
         'editions': {'Tex. Ct. App.': (date(1876, 1, 1), date(1891, 12, 31))},
         'mlz_jurisdiction': 'us;tx'},],
    'White & W.':
        [{'name': 'Condensed Reports of Decisions in Civil Causes in the Court of Appeals of Texas (White & Wilson)',
         'variations': {},
         'editions': {'White & W.': (date(1876, 1, 1), date(1883, 12, 31))},
         'mlz_jurisdiction': 'us;tx'},],
    'Wilson':
        [{'name': 'Condensed Reports of Decisions in Civil Causes in the Court of Appeals of Texas (Wilson)',
         'variations': {},
         'editions': {'Wilson': (date(1883, 1, 1), date(1892, 12, 31))},
         'mlz_jurisdiction': 'us;tx'},],
    'Tex. Civ. App.':
        [{'name': 'Texas Civil Appeals Reports',
         'variations': {},
         'editions': {'Tex. Civ. App.': (date(1892, 1, 1), date(1911, 12, 31))},
         'mlz_jurisdiction': 'us;tx'},],

    'Utah':
        [{'name': 'Utah Reports',
         'variations': {},
         # Needs research
         'editions': {'Utah': (date(1851, 1, 1), date(1974, 12, 31)),
                      'Utah 2d': (date(1851, 1, 1), date(1974, 12, 31))},
         'mlz_jurisdiction': 'us;ut'},],

    'Vt.':
        [{'name': 'Vermont Reports',
         'variations': {},
         'editions': {'Vt.': (date(1826, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;vt'},],
    'Aik.':
        [{'name': 'Vermont Reports, Aikens',
         'variations': {},
         'editions': {'Aik.': (date(1825, 1, 1), date(1828, 12, 31))},
         'mlz_jurisdiction': 'us;vt'},],
    'D. Chip.':
        [{'name': 'Vermont Reports, Chipman, D.',
         'variations': {},
         'editions': {'D. Chip.': (date(1789, 1, 1), date(1824, 12, 31))},
         'mlz_jurisdiction': 'us;vt'},],
    'Brayt.':
        [{'name': 'Vermont Reports, Brayton',
         'variations': {},
         'editions': {'Brayt.': (date(1815, 1, 1), date(1819, 12, 31))},
         'mlz_jurisdiction': 'us;vt'},],
    'Tyl.':
        [{'name': 'Vermont Reports, Tyler',
         'variations': {},
         'editions': {'Tyl.': (date(1800, 1, 1), date(1803, 12, 31))},
         'mlz_jurisdiction': 'us;vt'},],
    'N. Chip.':
        [{'name': 'Vermont Reports, Chipman, N.',
         'variations': {},
         'editions': {'N. Chip.': (date(1789, 1, 1), date(1791, 12, 31))},
         'mlz_jurisdiction': 'us;vt'},],

    'Va.':
        [{'name': 'Virginia Reports',
         'variations': {},
         'editions': {'Va.': (date(1880, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;va'},],
    'Gratt.':
        [{'name': 'Virginia Reports, Grattan',
         'variations': {},
         'editions': {'Gratt.': (date(1844, 1, 1), date(1880, 12, 31))},
         'mlz_jurisdiction': 'us;va'},],
    # For additional VA reporter, see 'Rob.' key
    'Leigh':
        [{'name': 'Virginia Reports, Leigh',
         'variations': {},
         'editions': {'Leigh': (date(1829, 1, 1), date(1842, 12, 31))},
         'mlz_jurisdiction': 'us;va'},],
    'Rand.':
        [{'name': 'Virginia Reports, Randolph',
         'variations': {},
         'editions': {'Rand.': (date(1821, 1, 1), date(1828, 12, 31))},
         'mlz_jurisdiction': 'us;va'},],
    'Gilmer':
        [{'name': 'Virginia Reports, Gilmer',
         'variations': {},
         'editions': {'Gilmer': (date(1820, 1, 1), date(1821, 12, 31))},
         'mlz_jurisdiction': 'us;va'},],
    'Munf.':
        [{'name': 'Virginia Reports, Munford',
         'variations': {},
         'editions': {'Monf.': (date(1810, 1, 1), date(1820, 12, 31))},
         'mlz_jurisdiction': 'us;va'},],
    'Hen. & M.':
        [{'name': 'Virginia Reports, Hening & Munford',
         'variations': {},
         'editions': {'Hen. & M.': (date(1806, 1, 1), date(1810, 12, 31))},
         'mlz_jurisdiction': 'us;va'},],
    'Call':
        [{'name': 'Virginia Reports, Call',
         'variations': {},
         'editions': {'Call': (date(1779, 1, 1), date(1825, 12, 31))},
         'mlz_jurisdiction': 'us;va'},],
    'Va. Cas.':
        [{'name': 'Virginia Cases, Criminal',
         'variations': {},
         'editions': {'Va. Cas.': (date(1789, 1, 1), date(1826, 12, 31))},
         'mlz_jurisdiction': 'us;va'},],
    'Wash.':
        [{'name': 'Virginia Reports, Washington',
          'variations': {},
          'editions': {'Wash.': (date(1790, 1, 1), date(1796, 12, 31))},
          'mlz_jurisdiction': 'us;va'},
         {'name': 'Washington Reports',
          'variations': {'Wn.2d': 'Wash. 2d',
                         'Wn. 2d': 'Wash. 2d',
                         'Wn': 'Wash.', },
          # Needs research
          'editions': {'Wash.': (date(1889, 1, 1), date.today()),
                       'Wash. 2d': (date(1889, 1, 1), date.today())},
          'mlz_jurisdiction': 'us;wa'},],
    'Va. App.':
        [{'name': 'Virginia Court of Appeals Reports',
         'variations': {},
         'editions': {'Va. App.': (date(1985, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;va'},],

    # For additional WA reporter, see 'Wash.'

    'Wash. Terr.':
        [{'name': 'Washington Territory Reports',
         'variations': {'Wn. Terr.': 'Wash. Terr.'}, # Normalize Washington reporters (local rules?)
         'editions': {'Wash. Terr.': (date(1854, 1, 1), date(1888, 12, 31))},
         'mlz_jurisdiction': 'us;wa'},],
    'Wash. App.':
        [{'name': 'Washington Appellate Reports',
         'variations': {'Wn.App.': 'Wash. App.',
                        'Wn. App.': 'Wash. App.', },
         'editions': {'Wash. App.': (date(1969, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;wa'},],

    'W. Va.':
        [{'name': 'West Virginia Reports',
         'variations': {},
         'editions': {'W. Va': (date(1864, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;wv'},],

    'Wis.':
        [{'name': 'Wisconsin Reports',
         'variations': {'Wis.2d': 'Wis. 2d', },
         # Needs research
         'editions': {'Wis.': (date(1853, 1, 1), date.today()),
                      'Wis. 2d': (date(1853, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;wi'},],
    'Pin.':
        [{'name': 'Wisconsin Reports, Pinney',
         'variations': {},
         'editions': {'Pin.': (date(1839, 1, 1), date(1852, 12, 31))},
         'mlz_jurisdiction': 'us;wi'},],
    'Chand.':
        [{'name': 'Wisconsin Reports, Chandler',
         'variations': {},
         'editions': {'Chand.': (date(1849, 1, 1), date(1852, 12, 31))},
         'mlz_jurisdiction': 'us;wi'},],
    'Bur.':
        [{'name': 'Wisconsin Reports, Burnett',
         'variations': {},
         'editions': {'Bur.': (date(1841, 1, 1), date(1843, 12, 31))},
         'mlz_jurisdiction': 'us;wi'},],

    'Wyo.':
        [{'name': 'Wyoming Reports',
         'variations': {},
         'editions': {'Wyo.': (date(1870, 1, 1), date(1959, 12, 31))},
         'mlz_jurisdiction': 'us;wy'},],

    #####################################
    # Other United States Jurisdictions #
    #####################################
    'Am. Samoa':
        [{'name': 'American Samoa Reports',
         'variations': {},
         # Needs research
         'editions': {'Am. Samoa': (date(1900, 1, 1), date.today()),
                      'Am. Samoa 2d': (date(1900, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;am'},],

    'Guam':
        [{'name': 'Guam Reports',
         'variations': {},
         'editions': {'Guam': (date(1955, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;gu'},],

    'Navajo Rptr.':
        [{'name': 'Navajo Reporter',
         'variations': {},
         'editions': {'Navajo Rptr.': (date(1969, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],

    'N. Mar. I.':
        [{'name': 'Northern Mariana Islands Reporter',
         'variations': {},
         'editions': {'N. Mar. I.': (date(1989, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],
    'N. Mar. I. Commw. Rptr.':
        [{'name': 'Northern Mariana Islands Commonwealth Reporter',
         'variations': {},
         'editions': {'N. Mar. I. Commw. Rptr.': (date(1979, 1, 1), date.today())},
         'mlz_jurisdiction': 'us'},],

    'P.R.R.':
        [{'name': 'Puerto Rico Reports',
         'variations': {'Puerto Rico': 'P.R.R.',
                        'P.R.': 'P.R.R.'},
         'editions': {'P.R.R.': (date(1899, 1, 1), date(1978, 12, 31))},
         'mlz_jurisdiction': 'us;pr'},],
    'P.R. Offic. Trans.':
        [{'name': 'Official Translations of the Opinions of the Supreme Court of Puerto Rico',
         'variations': {},
         'editions': {'P.R. Offic. Trans.': (date(1978, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;pr'},],
    'P.R. Dec.':
        [{'name': 'Decisiones de Puerto Rico',
         'variations': {},
         'editions': {'P.R. Dec.': (date(1899, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;pr'},],
    'P.R. Sent.':
        [{'name': 'Sentencias del Tribunal Supremo de Puerto Rico',
         'variations': {},
         'editions': {'P.R. Sent.': (date(1899, 1, 1), date(1902, 12, 31))},
         'mlz_jurisdiction': 'us;pr'},],

    'V.I':
        [{'name': 'Virgin Islands Reports',
         'variations': {},
         'editions': {'V.I.': (date(1917, 1, 1), date.today())},
         'mlz_jurisdiction': 'us;'},],
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
#REPORTERS.extend(NEUTRAL_CITATIONS)

# We normalize spaces and other errors people make
# See note on REPORTERS for ordering of this list.
VARIATIONS = {

    # State neutral citations
    '-Ohio-': 'Ohio',
}
