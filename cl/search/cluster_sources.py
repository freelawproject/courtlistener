class ClusterSources:
    COURT_WEBSITE = "C"
    PUBLIC_RESOURCE = "R"
    COURT_M_RESOURCE = "CR"
    LAWBOX = "L"
    LAWBOX_M_COURT = "LC"
    LAWBOX_M_RESOURCE = "LR"
    LAWBOX_M_COURT_RESOURCE = "LCR"
    MANUAL_INPUT = "M"
    INTERNET_ARCHIVE = "A"
    BRAD_HEATH_ARCHIVE = "H"
    COLUMBIA_ARCHIVE = "Z"
    HARVARD_CASELAW = "U"
    COURT_M_HARVARD = "CU"
    DIRECT_COURT_INPUT = "D"
    ANON_2020 = "Q"
    ANON_2020_M_HARVARD = "QU"
    COURT_M_RESOURCE_M_HARVARD = "CRU"
    DIRECT_COURT_INPUT_M_HARVARD = "DU"
    LAWBOX_M_HARVARD = "LU"
    LAWBOX_M_COURT_M_HARVARD = "LCU"
    LAWBOX_M_RESOURCE_M_HARVARD = "LRU"
    LAWBOX_M_COURT_RESOURCE_M_HARVARD = "LCRU"
    MANUAL_INPUT_M_HARVARD = "MU"
    PUBLIC_RESOURCE_M_HARVARD = "RU"
    COLUMBIA_M_INTERNET_ARCHIVE = "ZA"
    COLUMBIA_M_DIRECT_COURT_INPUT = "ZD"
    COLUMBIA_M_COURT = "ZC"
    COLUMBIA_M_BRAD_HEATH_ARCHIVE = "ZH"
    COLUMBIA_M_LAWBOX_COURT = "ZLC"
    COLUMBIA_M_LAWBOX_RESOURCE = "ZLR"
    COLUMBIA_M_LAWBOX_COURT_RESOURCE = "ZLCR"
    COLUMBIA_M_RESOURCE = "ZR"
    COLUMBIA_M_COURT_RESOURCE = "ZCR"
    COLUMBIA_M_LAWBOX = "ZL"
    COLUMBIA_M_MANUAL = "ZM"
    COLUMBIA_M_ANON_2020 = "ZQ"
    COLUMBIA_ARCHIVE_M_HARVARD = "ZU"
    COLUMBIA_M_LAWBOX_M_HARVARD = "ZLU"
    COLUMBIA_M_DIRECT_COURT_INPUT_M_HARVARD = "ZDU"
    COLUMBIA_M_LAWBOX_M_RESOURCE_M_HARVARD = "ZLRU"
    COLUMBIA_M_LAWBOX_M_COURT_RESOURCE_M_HARVARD = "ZLCRU"
    COLUMBIA_M_COURT_M_HARVARD = "ZCU"
    COLUMBIA_M_MANUAL_INPUT_M_HARVARD = "ZMU"
    COLUMBIA_M_PUBLIC_RESOURCE_M_HARVARD = "ZRU"
    COLUMBIA_M_LAWBOX_M_COURT_M_HARVARD = "ZLCU"
    RECAP = "G"
    SCANNING_PROJECT = "S"
    DIRECT_COURT_INPUT_M_SCANNING_PROJECT = "DS"
    COURT_M_SCANNING_PROJECT = "CS"
    PUBLIC_RESOURCE_M_SCANNING_PROJECT = "RS"
    LAWBOX_M_SCANNING_PROJECT = "LS"
    MANUAL_INPUT_M_SCANNING_PROJECT = "MS"
    INTERNET_ARCHIVE_M_SCANNING_PROJECT = "AS"
    BRAD_HEATH_ARCHIVE_M_SCANNING_PROJECT = "HS"
    COLUMBIA_ARCHIVE_M_SCANNING_PROJECT = "ZS"
    ANON_2020_M_SCANNING_PROJECT = "QS"
    ANON_2020_M_HARVARD_M_SCANNING_PROJECT = "QUS"
    HARVARD_M_SCANNING_PROJECT = "US"
    COURT_M_RESOURCE_M_SCANNING_PROJECT = "CRS"
    LAWBOX_M_COURT_M_SCANNING_PROJECT = "LCS"
    LAWBOX_M_RESOURCE_M_SCANNING_PROJECT = "LRS"
    LAWBOX_M_COURT_RESOURCE_M_SCANNING_PROJECT = "LCRS"
    COLUMBIA_M_INTERNET_ARCHIVE_M_SCANNING_PROJECT = "ZAS"
    COLUMBIA_M_BRAD_HEATH_ARCHIVE_M_SCANNING_PROJECT = "ZHS"
    COLUMBIA_M_DIRECT_COURT_INPUT_M_SCANNING_PROJECT = "ZDS"
    COLUMBIA_M_COURT_M_SCANNING_PROJECT = "ZCS"
    COLUMBIA_M_LAWBOX_COURT_M_SCANNING_PROJECT = "ZLCS"
    COLUMBIA_M_LAWBOX_RESOURCE_M_SCANNING_PROJECT = "ZLRS"
    COLUMBIA_M_LAWBOX_COURT_RESOURCE_M_SCANNING_PROJECT = "ZLCRS"
    COLUMBIA_M_RESOURCE_M_SCANNING_PROJECT = "ZRS"
    COLUMBIA_M_COURT_RESOURCE_M_SCANNING_PROJECT = "ZCRS"
    COLUMBIA_M_LAWBOX_M_SCANNING_PROJECT = "ZLS"
    COLUMBIA_M_MANUAL_M_SCANNING_PROJECT = "ZMS"
    COLUMBIA_M_ANON_2020_M_SCANNING_PROJECT = "ZQS"
    COLUMBIA_ARCHIVE_M_HARVARD_M_SCANNING_PROJECT = "ZUS"
    COLUMBIA_M_LAWBOX_M_HARVARD_M_SCANNING_PROJECT = "ZLUS"
    COLUMBIA_M_DIRECT_COURT_INPUT_M_HARVARD_M_SCANNING_PROJECT = "ZDUS"
    COLUMBIA_M_LAWBOX_M_RESOURCE_M_HARVARD_M_SCANNING_PROJECT = "ZLRUS"
    COLUMBIA_M_LAWBOX_M_COURT_RESOURCE_M_HARVARD_M_SCANNING_PROJECT = "ZLCRUS"
    COLUMBIA_M_COURT_M_HARVARD_M_SCANNING_PROJECT = "ZCUS"
    COLUMBIA_M_MANUAL_INPUT_M_HARVARD_M_SCANNING_PROJECT = "ZMUS"
    COLUMBIA_M_PUBLIC_RESOURCE_M_HARVARD_M_SCANNING_PROJECT = "ZRUS"
    COLUMBIA_M_LAWBOX_M_COURT_M_HARVARD_M_SCANNING_PROJECT = "ZLCUS"
    COURT_M_HARVARD_M_SCANNING_PROJECT = "CUS"
    COURT_M_RESOURCE_M_HARVARD_M_SCANNING_PROJECT = "CRUS"
    DIRECT_COURT_INPUT_M_HARVARD_M_SCANNING_PROJECT = "DUS"
    LAWBOX_M_HARVARD_M_SCANNING_PROJECT = "LUS"
    LAWBOX_M_COURT_M_HARVARD_M_SCANNING_PROJECT = "LCUS"
    LAWBOX_M_RESOURCE_M_HARVARD_M_SCANNING_PROJECT = "LRUS"
    LAWBOX_M_COURT_RESOURCE_M_HARVARD_M_SCANNING_PROJECT = "LCRUS"
    MANUAL_INPUT_M_HARVARD_M_SCANNING_PROJECT = "MUS"
    PUBLIC_RESOURCE_M_HARVARD_M_SCANNING_PROJECT = "RUS"

    NAMES = (
        (COURT_WEBSITE, "court website"),
        (PUBLIC_RESOURCE, "public.resource.org"),
        (COURT_M_RESOURCE, "court website merged with resource.org"),
        (LAWBOX, "lawbox"),
        (LAWBOX_M_COURT, "lawbox merged with court"),
        (LAWBOX_M_RESOURCE, "lawbox merged with resource.org"),
        (LAWBOX_M_COURT_RESOURCE, "lawbox merged with court and resource.org"),
        (MANUAL_INPUT, "manual input"),
        (INTERNET_ARCHIVE, "internet archive"),
        (BRAD_HEATH_ARCHIVE, "brad heath archive"),
        (COLUMBIA_ARCHIVE, "columbia archive"),
        (COLUMBIA_M_INTERNET_ARCHIVE, "columbia merged with internet archive"),
        (
            COLUMBIA_M_DIRECT_COURT_INPUT,
            "columbia merged with direct court input",
        ),
        (COLUMBIA_M_COURT, "columbia merged with court"),
        (
            COLUMBIA_M_BRAD_HEATH_ARCHIVE,
            "columbia merged with brad heath archive",
        ),
        (COLUMBIA_M_LAWBOX_COURT, "columbia merged with lawbox and court"),
        (
            COLUMBIA_M_LAWBOX_RESOURCE,
            "columbia merged with lawbox and resource.org",
        ),
        (
            COLUMBIA_M_LAWBOX_COURT_RESOURCE,
            "columbia merged with lawbox, court, and resource.org",
        ),
        (COLUMBIA_M_RESOURCE, "columbia merged with resource.org"),
        (
            COLUMBIA_M_COURT_RESOURCE,
            "columbia merged with court and resource.org",
        ),
        (COLUMBIA_M_LAWBOX, "columbia merged with lawbox"),
        (COLUMBIA_M_MANUAL, "columbia merged with manual input"),
        (COLUMBIA_M_ANON_2020, "columbia merged with 2020 anonymous database"),
        (
            HARVARD_CASELAW,
            "Harvard, Library Innovation Lab Case Law Access Project",
        ),
        (COURT_M_HARVARD, "court website merged with Harvard"),
        (DIRECT_COURT_INPUT, "direct court input"),
        (ANON_2020, "2020 anonymous database"),
        (ANON_2020_M_HARVARD, "2020 anonymous database merged with Harvard"),
        (
            COURT_M_RESOURCE_M_HARVARD,
            "court website merged with public.resource.org and Harvard",
        ),
        (
            DIRECT_COURT_INPUT_M_HARVARD,
            "direct court input merged with Harvard",
        ),
        (LAWBOX_M_HARVARD, "lawbox merged with Harvard"),
        (
            LAWBOX_M_COURT_M_HARVARD,
            "Lawbox merged with court website and Harvard",
        ),
        (
            LAWBOX_M_RESOURCE_M_HARVARD,
            "Lawbox merged with public.resource.org and with Harvard",
        ),
        (
            LAWBOX_M_COURT_RESOURCE_M_HARVARD,
            "Lawbox merged with court website, public.resource.org and Harvard",
        ),
        (MANUAL_INPUT_M_HARVARD, "Manual input merged with Harvard"),
        (PUBLIC_RESOURCE_M_HARVARD, "public.resource.org merged with Harvard"),
        (COLUMBIA_ARCHIVE_M_HARVARD, "columbia archive merged with Harvard"),
        (
            COLUMBIA_M_LAWBOX_M_HARVARD,
            "columbia archive merged with Lawbox and Harvard",
        ),
        (
            COLUMBIA_M_DIRECT_COURT_INPUT_M_HARVARD,
            "columbia archive merged with direct court input and Harvard",
        ),
        (
            COLUMBIA_M_LAWBOX_M_RESOURCE_M_HARVARD,
            "columbia archive merged with lawbox, public.resource.org and Harvard",
        ),
        (
            COLUMBIA_M_LAWBOX_M_COURT_RESOURCE_M_HARVARD,
            "columbia archive merged with lawbox, court website, public.resource.org and Harvard",
        ),
        (
            COLUMBIA_M_COURT_M_HARVARD,
            "columbia archive merged with court website and Harvard",
        ),
        (
            COLUMBIA_M_MANUAL_INPUT_M_HARVARD,
            "columbia archive merged with manual input and Harvard",
        ),
        (
            COLUMBIA_M_PUBLIC_RESOURCE_M_HARVARD,
            "columbia archive merged with public.resource.org and Harvard",
        ),
        (
            COLUMBIA_M_LAWBOX_M_COURT_M_HARVARD,
            "columbia archive merged with lawbox, court website and Harvard",
        ),
        (
            RECAP,
            "recap",
        ),
        (
            SCANNING_PROJECT,
            "scanning project",
        ),
        (
            DIRECT_COURT_INPUT_M_SCANNING_PROJECT,
            "direct court input merged with scanning project",
        ),
        (
            COURT_M_SCANNING_PROJECT,
            "court website merged with scanning project",
        ),
        (
            PUBLIC_RESOURCE_M_SCANNING_PROJECT,
            "public.resource.org merged with scanning project",
        ),
        (LAWBOX_M_SCANNING_PROJECT, "lawbox merged with scanning project"),
        (
            MANUAL_INPUT_M_SCANNING_PROJECT,
            "manual input merged with scanning project",
        ),
        (
            INTERNET_ARCHIVE_M_SCANNING_PROJECT,
            "internet archive merged with scanning project",
        ),
        (
            BRAD_HEATH_ARCHIVE_M_SCANNING_PROJECT,
            "brad heath archive merged with scanning project",
        ),
        (
            COLUMBIA_ARCHIVE_M_SCANNING_PROJECT,
            "columbia archive merged with scanning project",
        ),
        (
            ANON_2020_M_SCANNING_PROJECT,
            "2020 anonymous database merged with scanning project",
        ),
        (
            ANON_2020_M_HARVARD_M_SCANNING_PROJECT,
            "2020 anonymous database merged with Harvard and scanning project",
        ),
        (HARVARD_M_SCANNING_PROJECT, "Harvard merged with scanning project"),
        (
            COURT_M_RESOURCE_M_SCANNING_PROJECT,
            "court website merged with public.resource.org and scanning project",
        ),
        (
            LAWBOX_M_COURT_M_SCANNING_PROJECT,
            "lawbox merged with court website and scanning project",
        ),
        (
            LAWBOX_M_RESOURCE_M_SCANNING_PROJECT,
            "lawbox merged with public.resource.org and scanning project",
        ),
        (
            LAWBOX_M_COURT_RESOURCE_M_SCANNING_PROJECT,
            "lawbox merged with court, public.resource.org and scanning project",
        ),
        (
            COLUMBIA_M_INTERNET_ARCHIVE_M_SCANNING_PROJECT,
            "columbia merged with internet archive and scanning project",
        ),
        (
            COLUMBIA_M_BRAD_HEATH_ARCHIVE_M_SCANNING_PROJECT,
            "columbia merged with brad heath archive and scanning project",
        ),
        (
            COLUMBIA_M_DIRECT_COURT_INPUT_M_SCANNING_PROJECT,
            "columbia merged with direct court input and scanning project",
        ),
        (
            COLUMBIA_M_COURT_M_SCANNING_PROJECT,
            "columbia merged with court and scanning project",
        ),
        (
            COLUMBIA_M_LAWBOX_COURT_M_SCANNING_PROJECT,
            "columbia merged with lawbox, court and scanning project",
        ),
        (
            COLUMBIA_M_LAWBOX_RESOURCE_M_SCANNING_PROJECT,
            "columbia merged with lawbox, public.resource.org and scanning project",
        ),
        (
            COLUMBIA_M_LAWBOX_COURT_RESOURCE_M_SCANNING_PROJECT,
            "columbia merged with lawbox, court, public.resource.org and scanning project",
        ),
        (
            COLUMBIA_M_RESOURCE_M_SCANNING_PROJECT,
            "columbia merged with public.resource.org and scanning project",
        ),
        (
            COLUMBIA_M_COURT_RESOURCE_M_SCANNING_PROJECT,
            "columbia merged with court, public.resource.org and scanning project",
        ),
        (
            COLUMBIA_M_LAWBOX_M_SCANNING_PROJECT,
            "columbia merged with lawbox and scanning project",
        ),
        (
            COLUMBIA_M_MANUAL_M_SCANNING_PROJECT,
            "columbia merged with manual input and scanning project",
        ),
        (
            COLUMBIA_M_ANON_2020_M_SCANNING_PROJECT,
            "columbia merged with 2020 anonymous database and scanning project",
        ),
        (
            COLUMBIA_ARCHIVE_M_HARVARD_M_SCANNING_PROJECT,
            "columbia archive merged with Harvard and scanning project",
        ),
        (
            COLUMBIA_M_LAWBOX_M_HARVARD_M_SCANNING_PROJECT,
            "columbia merged with lawbox and Harvard and scanning project",
        ),
        (
            COLUMBIA_M_DIRECT_COURT_INPUT_M_HARVARD_M_SCANNING_PROJECT,
            "columbia merged with direct court input, Harvard and scanning project",
        ),
        (
            COLUMBIA_M_LAWBOX_M_RESOURCE_M_HARVARD_M_SCANNING_PROJECT,
            "columbia merged with lawbox, public.resource.org and Harvard and scanning project",
        ),
        (
            COLUMBIA_M_LAWBOX_M_COURT_RESOURCE_M_HARVARD_M_SCANNING_PROJECT,
            "columbia merged with lawbox, court, public.resource.org and Harvard and scanning project",
        ),
        (
            COLUMBIA_M_COURT_M_HARVARD_M_SCANNING_PROJECT,
            "columbia merged with court, Harvard and scanning project",
        ),
        (
            COLUMBIA_M_MANUAL_INPUT_M_HARVARD_M_SCANNING_PROJECT,
            "columbia merged with manual input, Harvard and scanning project",
        ),
        (
            COLUMBIA_M_PUBLIC_RESOURCE_M_HARVARD_M_SCANNING_PROJECT,
            "columbia merged with public.resource.org, Harvard and scanning project",
        ),
        (
            COLUMBIA_M_LAWBOX_M_COURT_M_HARVARD_M_SCANNING_PROJECT,
            "columbia merged with lawbox, court and Harvard and scanning project",
        ),
        (
            COURT_M_HARVARD_M_SCANNING_PROJECT,
            "court website merged with Harvard and scanning project",
        ),
        (
            COURT_M_RESOURCE_M_HARVARD_M_SCANNING_PROJECT,
            "court website merged with public.resource.org, Harvard and scanning project",
        ),
        (
            DIRECT_COURT_INPUT_M_HARVARD_M_SCANNING_PROJECT,
            "direct court input merged with Harvard and scanning project",
        ),
        (
            LAWBOX_M_HARVARD_M_SCANNING_PROJECT,
            "lawbox merged with Harvard and scanning project",
        ),
        (
            LAWBOX_M_COURT_M_HARVARD_M_SCANNING_PROJECT,
            "lawbox merged with court, Harvard and scanning project",
        ),
        (
            LAWBOX_M_RESOURCE_M_HARVARD_M_SCANNING_PROJECT,
            "lawbox merged with public.resource.org, Harvard and scanning project",
        ),
        (
            LAWBOX_M_COURT_RESOURCE_M_HARVARD_M_SCANNING_PROJECT,
            "lawbox merged with court, public.resource.org, Harvard and scanning project",
        ),
        (
            MANUAL_INPUT_M_HARVARD_M_SCANNING_PROJECT,
            "manual input merged with Harvard and scanning project",
        ),
        (
            PUBLIC_RESOURCE_M_HARVARD_M_SCANNING_PROJECT,
            "public.resource.org merged with Harvard and scanning project",
        ),
    )

    # use a frozenset since the order of characters is arbitrary
    parts_to_source_mapper = {frozenset(name[0]): name[0] for name in NAMES}

    @classmethod
    def merge_sources(cls, source1: str, source2: str) -> str:
        """Merge source values

        Use this to merge sources when merging clusters

        :param source1: a source
        :param source2: other source
        :return: a source which merges the input sources
        """
        if source1 in source2:
            return source2
        if source2 in source1:
            return source1

        unique_parts = frozenset(source1 + source2)
        if cls.parts_to_source_mapper.get(unique_parts):
            return cls.parts_to_source_mapper.get(unique_parts)

        # Unexpected case
        if len(source1) > len(source2):
            return source1
        return source2
