class DocketSources:
    _RECAP_SOURCES_CACHE = None
    _NON_RECAP_SOURCES_CACHE = None
    _NON_SCRAPER_SOURCES_CACHE = None
    _NON_COLUMBIA_SOURCES_CACHE = None
    _NON_HARVARD_SOURCES_CACHE = None
    _NON_IDB_SOURCES_CACHE = None
    _NON_ANON_2020_SOURCES_CACHE = None

    # The source values are additive. That is, if you get content from a new
    # source, you can add it to the previous one, and have a combined value.
    # For example, if you start with a RECAP docket (1), then add scraped
    # content (2), you can arrive at a combined docket (3) because 1 + 2 = 3.
    # Put another way, this is a bitmask. We should eventually re-do it as a
    # bitfield using, e.g. https://github.com/disqus/django-bitfield
    DEFAULT = 0
    RECAP = 1
    SCRAPER = 2
    RECAP_AND_SCRAPER = 3
    COLUMBIA = 4
    COLUMBIA_AND_RECAP = 5
    COLUMBIA_AND_SCRAPER = 6
    COLUMBIA_AND_RECAP_AND_SCRAPER = 7
    IDB = 8
    RECAP_AND_IDB = 9
    SCRAPER_AND_IDB = 10
    RECAP_AND_SCRAPER_AND_IDB = 11
    COLUMBIA_AND_IDB = 12
    COLUMBIA_AND_RECAP_AND_IDB = 13
    COLUMBIA_AND_SCRAPER_AND_IDB = 14
    COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB = 15
    HARVARD = 16
    HARVARD_AND_RECAP = 17
    SCRAPER_AND_HARVARD = 18
    RECAP_AND_SCRAPER_AND_HARVARD = 19
    HARVARD_AND_COLUMBIA = 20
    COLUMBIA_AND_RECAP_AND_HARVARD = 21
    COLUMBIA_AND_SCRAPER_AND_HARVARD = 22
    COLUMBIA_AND_RECAP_AND_SCRAPER_AND_HARVARD = 23
    IDB_AND_HARVARD = 24
    RECAP_AND_IDB_AND_HARVARD = 25
    SCRAPER_AND_IDB_AND_HARVARD = 26
    RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD = 27
    COLUMBIA_AND_IDB_AND_HARVARD = 28
    COLUMBIA_AND_RECAP_AND_IDB_AND_HARVARD = 29
    COLUMBIA_AND_SCRAPER_AND_IDB_AND_HARVARD = 30
    COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD = 31
    DIRECT_INPUT = 32
    RECAP_AND_DIRECT_INPUT = 33
    SCRAPER_AND_DIRECT_INPUT = 34
    RECAP_AND_SCRAPER_AND_DIRECT_INPUT = 35
    COLUMBIA_AND_DIRECT_INPUT = 36
    RECAP_AND_COLUMBIA_AND_DIRECT_INPUT = 37
    SCRAPER_AND_COLUMBIA_AND_DIRECT_INPUT = 38
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_DIRECT_INPUT = 39
    IDB_AND_DIRECT_INPUT = 40
    RECAP_AND_IDB_AND_DIRECT_INPUT = 41
    SCRAPER_AND_IDB_AND_DIRECT_INPUT = 42
    RECAP_AND_SCRAPER_AND_IDB_AND_DIRECT_INPUT = 43
    COLUMBIA_AND_IDB_AND_DIRECT_INPUT = 44
    RECAP_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT = 45
    SCRAPER_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT = 46
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT = 47
    DIRECT_INPUT_AND_HARVARD = 48
    RECAP_AND_HARVARD_AND_DIRECT_INPUT = 49
    SCRAPER_AND_HARVARD_AND_DIRECT_INPUT = 50
    RECAP_AND_SCRAPER_AND_HARVARD_AND_DIRECT_INPUT = 51
    COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT = 52
    RECAP_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT = 53
    SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT = 54
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT = 55
    IDB_AND_HARVARD_AND_DIRECT_INPUT = 56
    RECAP_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT = 57
    SCRAPER_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT = 58
    RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT = 59
    COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT = 60
    RECAP_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT = 61
    SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT = 62
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT = 63
    ANON_2020 = 64
    RECAP_AND_ANON_2020 = 65
    ANON_2020_AND_SCRAPER = 66
    RECAP_AND_SCRAPER_AND_ANON_2020 = 67
    COLUMBIA_AND_ANON_2020 = 68
    RECAP_AND_COLUMBIA_AND_ANON_2020 = 69
    SCRAPER_AND_COLUMBIA_AND_ANON_2020 = 70
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_ANON_2020 = 71
    IDB_AND_ANON_2020 = 72
    RECAP_AND_IDB_AND_ANON_2020 = 73
    SCRAPER_AND_IDB_AND_ANON_2020 = 74
    RECAP_AND_SCRAPER_AND_IDB_AND_ANON_2020 = 75
    COLUMBIA_AND_IDB_AND_ANON_2020 = 76
    RECAP_AND_COLUMBIA_AND_IDB_AND_ANON_2020 = 77
    SCRAPER_AND_COLUMBIA_AND_IDB_AND_ANON_2020 = 78
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_ANON_2020 = 79
    ANON_2020_AND_HARVARD = 80
    RECAP_AND_HARVARD_AND_ANON_2020 = 81
    ANON_2020_AND_SCRAPER_AND_HARVARD = 82
    RECAP_AND_SCRAPER_AND_HARVARD_AND_ANON_2020 = 83
    COLUMBIA_AND_HARVARD_AND_ANON_2020 = 84
    RECAP_AND_COLUMBIA_AND_HARVARD_AND_ANON_2020 = 85
    SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_ANON_2020 = 86
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_ANON_2020 = 87
    IDB_AND_HARVARD_AND_ANON_2020 = 88
    RECAP_AND_IDB_AND_HARVARD_AND_ANON_2020 = 89
    SCRAPER_AND_IDB_AND_HARVARD_AND_ANON_2020 = 90
    RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD_AND_ANON_2020 = 91
    COLUMBIA_AND_IDB_AND_HARVARD_AND_ANON_2020 = 92
    RECAP_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_ANON_2020 = 93
    SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_ANON_2020 = 94
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_ANON_2020 = 95
    DIRECT_INPUT_AND_ANON_2020 = 96
    RECAP_AND_DIRECT_INPUT_AND_ANON_2020 = 97
    SCRAPER_AND_DIRECT_INPUT_AND_ANON_2020 = 98
    RECAP_AND_SCRAPER_AND_DIRECT_INPUT_AND_ANON_2020 = 99
    COLUMBIA_AND_DIRECT_INPUT_AND_ANON_2020 = 100
    RECAP_AND_COLUMBIA_AND_DIRECT_INPUT_AND_ANON_2020 = 101
    SCRAPER_AND_COLUMBIA_AND_DIRECT_INPUT_AND_ANON_2020 = 102
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_DIRECT_INPUT_AND_ANON_2020 = 103
    IDB_AND_DIRECT_INPUT_AND_ANON_2020 = 104
    RECAP_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020 = 105
    SCRAPER_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020 = 106
    RECAP_AND_SCRAPER_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020 = 107
    COLUMBIA_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020 = 108
    RECAP_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020 = 109
    SCRAPER_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020 = 110
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020 = 111
    HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 112
    RECAP_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 113
    SCRAPER_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 114
    RECAP_AND_SCRAPER_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 115
    COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 116
    RECAP_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 117
    SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 118
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = (
        119
    )
    IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 120
    RECAP_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 121
    SCRAPER_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 122
    RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 123
    COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 124
    RECAP_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = 125
    SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = (
        126
    )
    RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020 = (
        127
    )
    SOURCE_CHOICES = (
        (DEFAULT, "Default"),
        (RECAP, "RECAP"),
        (SCRAPER, "Scraper"),
        (RECAP_AND_SCRAPER, "RECAP and Scraper"),
        (COLUMBIA, "Columbia"),
        (COLUMBIA_AND_SCRAPER, "Columbia and Scraper"),
        (COLUMBIA_AND_RECAP, "Columbia and RECAP"),
        (COLUMBIA_AND_RECAP_AND_SCRAPER, "Columbia, RECAP, and Scraper"),
        (IDB, "Integrated Database"),
        (RECAP_AND_IDB, "RECAP and IDB"),
        (SCRAPER_AND_IDB, "Scraper and IDB"),
        (RECAP_AND_SCRAPER_AND_IDB, "RECAP, Scraper, and IDB"),
        (COLUMBIA_AND_IDB, "Columbia and IDB"),
        (COLUMBIA_AND_RECAP_AND_IDB, "Columbia, RECAP, and IDB"),
        (COLUMBIA_AND_SCRAPER_AND_IDB, "Columbia, Scraper, and IDB"),
        (
            COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB,
            "Columbia, RECAP, Scraper, and IDB",
        ),
        (HARVARD, "Harvard"),
        (HARVARD_AND_RECAP, "Harvard and RECAP"),
        (SCRAPER_AND_HARVARD, "Scraper and Harvard"),
        (RECAP_AND_SCRAPER_AND_HARVARD, "RECAP, Scraper and Harvard"),
        (HARVARD_AND_COLUMBIA, "Harvard and Columbia"),
        (COLUMBIA_AND_RECAP_AND_HARVARD, "Columbia, RECAP, and Harvard"),
        (COLUMBIA_AND_SCRAPER_AND_HARVARD, "Columbia, Scraper, and Harvard"),
        (
            COLUMBIA_AND_RECAP_AND_SCRAPER_AND_HARVARD,
            "Columbia, RECAP, Scraper, and Harvard",
        ),
        (IDB_AND_HARVARD, "IDB and Harvard"),
        (RECAP_AND_IDB_AND_HARVARD, "RECAP, IDB and Harvard"),
        (SCRAPER_AND_IDB_AND_HARVARD, "Scraper, IDB and Harvard"),
        (
            RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD,
            "RECAP, Scraper, IDB and Harvard",
        ),
        (COLUMBIA_AND_IDB_AND_HARVARD, "Columbia, IDB, and Harvard"),
        (
            COLUMBIA_AND_RECAP_AND_IDB_AND_HARVARD,
            "Columbia, Recap, IDB, and Harvard",
        ),
        (
            COLUMBIA_AND_SCRAPER_AND_IDB_AND_HARVARD,
            "Columbia, Scraper, IDB, and Harvard",
        ),
        (
            COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD,
            "Columbia, Recap, Scraper, IDB, and Harvard",
        ),
        (DIRECT_INPUT, "Direct court input"),
        (RECAP_AND_DIRECT_INPUT, "RECAP and Direct court input"),
        (SCRAPER_AND_DIRECT_INPUT, "Scraper and Direct court input"),
        (
            RECAP_AND_SCRAPER_AND_DIRECT_INPUT,
            "RECAP, Scraper, and Direct court input",
        ),
        (COLUMBIA_AND_DIRECT_INPUT, "Columbia and Direct court input"),
        (
            RECAP_AND_COLUMBIA_AND_DIRECT_INPUT,
            "RECAP, Columbia, and Direct court input",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_DIRECT_INPUT,
            "Scraper, Columbia, and Direct court input",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_DIRECT_INPUT,
            "RECAP, Scraper, Columbia, and Direct court input",
        ),
        (IDB_AND_DIRECT_INPUT, "IDB and Direct court input"),
        (
            RECAP_AND_IDB_AND_DIRECT_INPUT,
            "RECAP, IDB, and Direct court input",
        ),
        (
            SCRAPER_AND_IDB_AND_DIRECT_INPUT,
            "Scraper, IDB, and Direct court input",
        ),
        (
            RECAP_AND_SCRAPER_AND_IDB_AND_DIRECT_INPUT,
            "RECAP, Scraper, IDB, and Direct court input",
        ),
        (
            COLUMBIA_AND_IDB_AND_DIRECT_INPUT,
            "Columbia, IDB, and Direct court input",
        ),
        (
            RECAP_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT,
            "RECAP, Columbia, IDB, and Direct court input",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT,
            "Scraper, Columbia, IDB, and Direct court input",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT,
            "RECAP, Scraper, Columbia, IDB, and Direct court input",
        ),
        (DIRECT_INPUT_AND_HARVARD, "Direct court input and Harvard"),
        (
            RECAP_AND_HARVARD_AND_DIRECT_INPUT,
            "RECAP, Harvard, and Direct court input",
        ),
        (
            SCRAPER_AND_HARVARD_AND_DIRECT_INPUT,
            "Scraper, Harvard, and Direct court input",
        ),
        (
            RECAP_AND_SCRAPER_AND_HARVARD_AND_DIRECT_INPUT,
            "RECAP, Scraper, Harvard, and Direct court input",
        ),
        (
            COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT,
            "Columbia, Harvard, and Direct court input",
        ),
        (
            RECAP_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT,
            "RECAP, Columbia, Harvard, and Direct court input",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT,
            "Scraper, Columbia, Harvard, and Direct court input",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT,
            "RECAP, Scraper, Columbia, Harvard, and Direct court input",
        ),
        (
            IDB_AND_HARVARD_AND_DIRECT_INPUT,
            "IDB, Harvard, and Direct court input",
        ),
        (
            RECAP_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT,
            "RECAP, IDB, Harvard, and Direct court input",
        ),
        (
            SCRAPER_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT,
            "Scraper, IDB, Harvard, and Direct court input",
        ),
        (
            RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT,
            "RECAP, Scraper, IDB, Harvard, and Direct court input",
        ),
        (
            COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT,
            "Columbia, IDB, Harvard, and Direct court input",
        ),
        (
            RECAP_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT,
            "RECAP, Columbia, IDB, Harvard, and Direct court input",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT,
            "Scraper, Columbia, IDB, Harvard, and Direct court input",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT,
            "RECAP, Scraper, Columbia, IDB, Harvard, and Direct court input",
        ),
        (ANON_2020, "2020 anonymous database"),
        (IDB_AND_ANON_2020, "IDB and 2020 anonymous database"),
        (ANON_2020_AND_SCRAPER, "2020 anonymous database and Scraper"),
        (
            RECAP_AND_SCRAPER_AND_ANON_2020,
            "RECAP, Scraper, and 2020 anonymous database",
        ),
        (COLUMBIA_AND_ANON_2020, "Columbia and 2020 anonymous database"),
        (
            RECAP_AND_COLUMBIA_AND_ANON_2020,
            "RECAP, Columbia, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_ANON_2020,
            "Scraper, Columbia, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_ANON_2020,
            "RECAP, Scraper, Columbia, and 2020 anonymous database",
        ),
        (IDB_AND_ANON_2020, "IDB and 2020 anonymous database"),
        (
            RECAP_AND_IDB_AND_ANON_2020,
            "RECAP, IDB, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_IDB_AND_ANON_2020,
            "Scraper, IDB, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_IDB_AND_ANON_2020,
            "RECAP, Scraper, IDB, and 2020 anonymous database",
        ),
        (
            COLUMBIA_AND_IDB_AND_ANON_2020,
            "Columbia, IDB, and 2020 anonymous database",
        ),
        (
            RECAP_AND_COLUMBIA_AND_IDB_AND_ANON_2020,
            "RECAP, Columbia, IDB, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_IDB_AND_ANON_2020,
            "Scraper, Columbia, IDB, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_ANON_2020,
            "RECAP, Scraper, Columbia, IDB, and 2020 anonymous database",
        ),
        (ANON_2020_AND_HARVARD, "2020 anonymous database and Harvard"),
        (
            ANON_2020_AND_SCRAPER_AND_HARVARD,
            "2020 anonymous database, Scraper, and Harvard",
        ),
        (
            RECAP_AND_HARVARD_AND_ANON_2020,
            "RECAP, Harvard, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_HARVARD_AND_ANON_2020,
            "RECAP, Scraper, Harvard, and 2020 anonymous database",
        ),
        (
            COLUMBIA_AND_HARVARD_AND_ANON_2020,
            "Columbia, Harvard, and 2020 anonymous database",
        ),
        (
            RECAP_AND_COLUMBIA_AND_HARVARD_AND_ANON_2020,
            "RECAP, Columbia, Harvard, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_ANON_2020,
            "Scraper, Columbia, Harvard, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_ANON_2020,
            "RECAP, Scraper, Columbia, Harvard, and 2020 anonymous database",
        ),
        (
            IDB_AND_HARVARD_AND_ANON_2020,
            "IDB, Harvard, and 2020 anonymous database",
        ),
        (
            RECAP_AND_IDB_AND_HARVARD_AND_ANON_2020,
            "RECAP, IDB, Harvard, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_IDB_AND_HARVARD_AND_ANON_2020,
            "Scraper, IDB, Harvard, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD_AND_ANON_2020,
            "RECAP, Scraper, IDB, Harvard, and 2020 anonymous database",
        ),
        (
            COLUMBIA_AND_IDB_AND_HARVARD_AND_ANON_2020,
            "Columbia, IDB, Harvard, and 2020 anonymous database",
        ),
        (
            RECAP_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_ANON_2020,
            "RECAP, Columbia, IDB, Harvard, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_ANON_2020,
            "Scraper, Columbia, IDB, Harvard, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_ANON_2020,
            "RECAP, Scraper, Columbia, IDB, Harvard, and 2020 anonymous database",
        ),
        (
            DIRECT_INPUT_AND_ANON_2020,
            "Direct court input and 2020 anonymous database",
        ),
        (
            RECAP_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Direct court input, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_DIRECT_INPUT_AND_ANON_2020,
            "Scraper, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Scraper, Direct court input, and 2020 anonymous database",
        ),
        (
            COLUMBIA_AND_DIRECT_INPUT_AND_ANON_2020,
            "Columbia, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_COLUMBIA_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Columbia, Direct court input, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_DIRECT_INPUT_AND_ANON_2020,
            "Scraper, Columbia, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Scraper, Columbia, Direct court input, and 2020 anonymous database",
        ),
        (
            IDB_AND_DIRECT_INPUT_AND_ANON_2020,
            "IDB, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, IDB, Direct court input, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020,
            "Scraper, IDB, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Scraper, IDB, Direct court input, and 2020 anonymous database",
        ),
        (
            COLUMBIA_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020,
            "Columbia, IDB, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Columbia, IDB, Direct court input, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020,
            "Scraper, Columbia, IDB, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Scraper, Columbia, IDB, Direct court input, and 2020 anonymous database",
        ),
        (
            HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "Scraper, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Scraper, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "Columbia, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Columbia, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "Scraper, Columbia, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Scraper, Columbia, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "IDB, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, IDB, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "Scraper, IDB, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Scraper, IDB, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "Columbia, IDB, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Columbia, IDB, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "Scraper, Columbia, IDB, Harvard, Direct court input, and 2020 anonymous database",
        ),
        (
            RECAP_AND_SCRAPER_AND_COLUMBIA_AND_IDB_AND_HARVARD_AND_DIRECT_INPUT_AND_ANON_2020,
            "RECAP, Scraper, Columbia, IDB, Harvard, Direct court input, and 2020 anonymous database",
        ),
    )

    @classmethod
    def generate_source_group(
        cls, base_source: str, exclude: bool = False
    ) -> list[int]:
        """Generate a group of source IDs based on the inclusion or exclusion
        of a base source, selecting those that either include or exclude the
        specified base source in their names, as determined by the "exclude"
        parameter.

        :param base_source: The base source name to include or exclude.
        :param exclude: A flag indicating whether to exclude "True" or include
         "False "the base source.
        :return: A list of source IDs that match the filtering criteria.
        """

        dict_sources = {
            key: value
            for key, value in DocketSources.__dict__.items()
            if not key.startswith(("__", "_")) and isinstance(value, int)
        }
        if exclude:
            sources_group = [
                value
                for source, value in dict_sources.items()
                if base_source not in source.split("_AND_")
            ]
        else:
            sources_group = [
                value
                for source, value in dict_sources.items()
                if base_source in source.split("_AND_")
            ]
        return sources_group

    @classmethod
    def RECAP_SOURCES(cls) -> list[int]:
        if cls._RECAP_SOURCES_CACHE is None:
            cls._RECAP_SOURCES_CACHE = cls.generate_source_group(
                "RECAP", exclude=False
            )
        return cls._RECAP_SOURCES_CACHE

    @classmethod
    def NON_RECAP_SOURCES(cls) -> list[int]:
        if cls._NON_RECAP_SOURCES_CACHE is None:
            cls._NON_RECAP_SOURCES_CACHE = cls.generate_source_group(
                "RECAP", exclude=True
            )
        return cls._NON_RECAP_SOURCES_CACHE

    @classmethod
    def NON_SCRAPER_SOURCES(cls) -> list[int]:
        if cls._NON_SCRAPER_SOURCES_CACHE is None:
            cls._NON_SCRAPER_SOURCES_CACHE = cls.generate_source_group(
                "SCRAPER", exclude=True
            )
        return cls._NON_SCRAPER_SOURCES_CACHE

    @classmethod
    def NON_COLUMBIA_SOURCES(cls) -> list[int]:
        if cls._NON_COLUMBIA_SOURCES_CACHE is None:
            cls._NON_COLUMBIA_SOURCES_CACHE = cls.generate_source_group(
                "COLUMBIA", exclude=True
            )
        return cls._NON_COLUMBIA_SOURCES_CACHE

    @classmethod
    def NON_HARVARD_SOURCES(cls) -> list[int]:
        if cls._NON_HARVARD_SOURCES_CACHE is None:
            cls._NON_HARVARD_SOURCES_CACHE = cls.generate_source_group(
                "HARVARD", exclude=True
            )
        return cls._NON_HARVARD_SOURCES_CACHE

    @classmethod
    def NON_IDB_SOURCES(cls) -> list[int]:
        if cls._NON_IDB_SOURCES_CACHE is None:
            cls._NON_IDB_SOURCES_CACHE = cls.generate_source_group(
                "IDB", exclude=True
            )
        return cls._NON_IDB_SOURCES_CACHE

    @classmethod
    def NON_ANON_2020_SOURCES(cls) -> list[int]:
        if cls._NON_ANON_2020_SOURCES_CACHE is None:
            cls._NON_ANON_2020_SOURCES_CACHE = cls.generate_source_group(
                "ANON_2020", exclude=True
            )
        return cls._NON_ANON_2020_SOURCES_CACHE
