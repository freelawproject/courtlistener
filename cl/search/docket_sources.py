

class DocketSources:
    
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
    DIRECT_INPUT_AND_HARVARD = 48
    ANON_2020 = 64
    ANON_2020_AND_SCRAPER = 66
    ANON_2020_AND_HARVARD = 80
    ANON_2020_AND_SCRAPER_AND_HARVARD = 82
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
        (DIRECT_INPUT_AND_HARVARD, "Direct court input and Harvard"),
        (ANON_2020, "2020 anonymous database"),
        (ANON_2020_AND_SCRAPER, "2020 anonymous database and Scraper"),
        (ANON_2020_AND_HARVARD, "2020 anonymous database and Harvard"),
        (
            ANON_2020_AND_SCRAPER_AND_HARVARD,
            "2020 anonymous database, Scraper, and Harvard",
        ),
    )
    RECAP_SOURCES = [
        RECAP,
        RECAP_AND_SCRAPER,
        COLUMBIA_AND_RECAP,
        COLUMBIA_AND_RECAP_AND_SCRAPER,
        RECAP_AND_IDB,
        RECAP_AND_SCRAPER_AND_IDB,
        COLUMBIA_AND_RECAP_AND_IDB,
        COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB,
        HARVARD_AND_RECAP,
        RECAP_AND_SCRAPER_AND_HARVARD,
        COLUMBIA_AND_RECAP_AND_HARVARD,
        COLUMBIA_AND_RECAP_AND_SCRAPER_AND_HARVARD,
        RECAP_AND_IDB_AND_HARVARD,
        RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD,
        COLUMBIA_AND_RECAP_AND_IDB_AND_HARVARD,
        COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD,
    ]
    IDB_SOURCES = [
        IDB,
        RECAP_AND_IDB,
        SCRAPER_AND_IDB,
        RECAP_AND_SCRAPER_AND_IDB,
        COLUMBIA_AND_IDB,
        COLUMBIA_AND_RECAP_AND_IDB,
        COLUMBIA_AND_SCRAPER_AND_IDB,
        COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB,
    ]
    NON_RECAP_SOURCES = [
        SCRAPER,
        COLUMBIA,
        COLUMBIA_AND_SCRAPER,
        IDB,
        SCRAPER_AND_IDB,
        COLUMBIA_AND_IDB,
        COLUMBIA_AND_SCRAPER_AND_IDB,
        HARVARD,
        SCRAPER_AND_HARVARD,
        HARVARD_AND_COLUMBIA,
        COLUMBIA_AND_SCRAPER_AND_HARVARD,
        IDB_AND_HARVARD,
        SCRAPER_AND_IDB_AND_HARVARD,
        COLUMBIA_AND_IDB_AND_HARVARD,
        COLUMBIA_AND_SCRAPER_AND_IDB_AND_HARVARD,
    ]
    NON_SCRAPER_SOURCES = [
        DEFAULT,
        RECAP,
        COLUMBIA,
        COLUMBIA_AND_RECAP,
        IDB,
        RECAP_AND_IDB,
        COLUMBIA_AND_IDB,
        COLUMBIA_AND_RECAP_AND_IDB,
        HARVARD,
        HARVARD_AND_RECAP,
        HARVARD_AND_COLUMBIA,
        COLUMBIA_AND_RECAP_AND_HARVARD,
        IDB_AND_HARVARD,
        RECAP_AND_IDB_AND_HARVARD,
        COLUMBIA_AND_IDB_AND_HARVARD,
        COLUMBIA_AND_RECAP_AND_IDB_AND_HARVARD,
    ]
    NON_COLUMBIA_SOURCES = [
        DEFAULT,
        RECAP,
        SCRAPER,
        RECAP_AND_SCRAPER,
        IDB,
        RECAP_AND_IDB,
        SCRAPER_AND_IDB,
        RECAP_AND_SCRAPER_AND_IDB,
        HARVARD,
        HARVARD_AND_RECAP,
        SCRAPER_AND_HARVARD,
        RECAP_AND_SCRAPER_AND_HARVARD,
        IDB_AND_HARVARD,
        RECAP_AND_IDB_AND_HARVARD,
        SCRAPER_AND_IDB_AND_HARVARD,
        RECAP_AND_SCRAPER_AND_IDB_AND_HARVARD,
    ]
    NON_HARVARD_SOURCES = [
        DEFAULT,
        RECAP,
        SCRAPER,
        RECAP_AND_SCRAPER,
        COLUMBIA,
        COLUMBIA_AND_RECAP,
        COLUMBIA_AND_SCRAPER,
        COLUMBIA_AND_RECAP_AND_SCRAPER,
        IDB,
        RECAP_AND_IDB,
        SCRAPER_AND_IDB,
        RECAP_AND_SCRAPER_AND_IDB,
        COLUMBIA_AND_IDB,
        COLUMBIA_AND_RECAP_AND_IDB,
        COLUMBIA_AND_SCRAPER_AND_IDB,
        COLUMBIA_AND_RECAP_AND_SCRAPER_AND_IDB,
    ]
