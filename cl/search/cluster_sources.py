from django.core.exceptions import ValidationError


class ClusterSources:
    # Canonical ordering for deterministic source combination.
    # When merging sources, characters are sorted in this order.
    # This matches the explicit combination sources
    CANONICAL_ORDER = "ZLCRMDQAGUS"

    # Base sources
    COURT_WEBSITE = "C"
    PUBLIC_RESOURCE = "R"
    LAWBOX = "L"
    MANUAL_INPUT = "M"
    INTERNET_ARCHIVE = "A"
    COLUMBIA_ARCHIVE = "Z"
    HARVARD_CASELAW = "U"
    DIRECT_COURT_INPUT = "D"
    ANON_2020 = "Q"
    RECAP = "G"
    SCANNING_PROJECT = "S"

    # Combinations that exist in the database
    COURT_M_RESOURCE = "CR"
    LAWBOX_M_COURT = "LC"
    LAWBOX_M_RESOURCE = "LR"
    COURT_M_HARVARD = "CU"
    COURT_M_RESOURCE_M_HARVARD = "CRU"
    LAWBOX_M_HARVARD = "LU"
    LAWBOX_M_COURT_M_HARVARD = "LCU"
    LAWBOX_M_RESOURCE_M_HARVARD = "LRU"
    LAWBOX_M_COURT_RESOURCE_M_HARVARD = "LCRU"
    MANUAL_INPUT_M_HARVARD = "MU"
    PUBLIC_RESOURCE_M_HARVARD = "RU"
    COLUMBIA_M_COURT = "ZC"
    COLUMBIA_M_LAWBOX = "ZL"
    COLUMBIA_M_LAWBOX_COURT = "ZLC"
    COLUMBIA_ARCHIVE_M_HARVARD = "ZU"
    COLUMBIA_M_LAWBOX_M_HARVARD = "ZLU"
    COLUMBIA_M_COURT_M_HARVARD = "ZCU"
    COLUMBIA_M_LAWBOX_M_COURT_M_HARVARD = "ZLCU"

    # this will be exposed as help text on the API and elsewhere
    NAMES = (
        (COURT_WEBSITE, "court website"),
        (PUBLIC_RESOURCE, "public.resource.org"),
        (COURT_M_RESOURCE, "court website merged with resource.org"),
        (LAWBOX, "lawbox"),
        (LAWBOX_M_COURT, "lawbox merged with court"),
        (LAWBOX_M_RESOURCE, "lawbox merged with resource.org"),
        (MANUAL_INPUT, "manual input"),
        (INTERNET_ARCHIVE, "internet archive"),
        (COLUMBIA_ARCHIVE, "columbia archive"),
        (COLUMBIA_M_COURT, "columbia merged with court"),
        (COLUMBIA_M_LAWBOX, "columbia merged with lawbox"),
        (COLUMBIA_M_LAWBOX_COURT, "columbia merged with lawbox and court"),
        (
            HARVARD_CASELAW,
            "Harvard, Library Innovation Lab Case Law Access Project",
        ),
        (COURT_M_HARVARD, "court website merged with Harvard"),
        (DIRECT_COURT_INPUT, "direct court input"),
        (ANON_2020, "2020 anonymous database"),
        (
            COURT_M_RESOURCE_M_HARVARD,
            "court website merged with public.resource.org and Harvard",
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
            COLUMBIA_M_COURT_M_HARVARD,
            "columbia archive merged with court website and Harvard",
        ),
        (
            COLUMBIA_M_LAWBOX_M_COURT_M_HARVARD,
            "columbia archive merged with lawbox, court website and Harvard",
        ),
        (RECAP, "recap"),
        (SCANNING_PROJECT, "scanning project"),
    )

    # Map frozenset of characters to their canonical source string.
    # Used by merge_sources to preserve existing letter orderings.
    _value_set = {name[0] for name in NAMES}
    _parts_to_source = {frozenset(val): val for val in _value_set}

    # Map single characters to their human-readable base name
    _BASE_NAMES: dict[str, str] = {
        "C": "court website",
        "R": "public.resource.org",
        "L": "lawbox",
        "M": "manual input",
        "A": "internet archive",
        "Z": "columbia archive",
        "U": "Harvard",
        "D": "direct court input",
        "Q": "2020 anonymous database",
        "G": "recap",
        "S": "scanning project",
    }

    @classmethod
    def _canonical_combine(cls, chars: frozenset[str]) -> str:
        """Sort characters by CANONICAL_ORDER for a deterministic result.

        :param chars: frozenset of single-character source codes
        :return: combined source string in canonical order
        """
        return "".join(
            sorted(chars, key=lambda c: cls.CANONICAL_ORDER.index(c))
        )

    @classmethod
    def merge_sources(cls, source1: str, source2: str) -> str:
        """Merge source values

        Use this to merge sources when merging clusters

        :param source1: a source
        :param source2: other source
        :return: a source which merges the input sources
        """
        unique_parts = frozenset(source1 + source2)

        # If an explicit combination exists, use its established ordering
        if existing := cls._parts_to_source.get(unique_parts):
            return existing

        # Otherwise, combine deterministically using canonical order
        return cls._canonical_combine(unique_parts)

    @classmethod
    def get_display_name(cls, source: str) -> str:
        """Get human-readable name for any source combination.

        For known combinations, returns the name from NAMES.
        For dynamically-generated combinations, builds a descriptive name.

        :param source: source string (e.g. "CM", "ZLCRU")
        :return: human-readable description
        """
        names_dict = dict(cls.NAMES)
        if source in names_dict:
            return names_dict[source]

        # Build a name from components
        parts = [cls._BASE_NAMES.get(c, c) for c in source]
        if len(parts) <= 1:
            return parts[0] if parts else source
        return f"{parts[0]} merged with {', '.join(parts[1:])}"

    @classmethod
    def validate_source(cls, value: str) -> None:
        """Validate that a source string contains only known base source
        characters in canonical order.

        :param value: source string to validate
        :raises ValidationError: if value contains invalid characters or
            is not in canonical order
        """
        valid_chars = set(cls.CANONICAL_ORDER)
        if invalid := set(value) - valid_chars:
            raise ValidationError(f"Invalid source characters: {invalid}")
        expected = cls._canonical_combine(frozenset(value))
        if value != expected:
            raise ValidationError(
                f"Source must be in canonical order: {expected}"
            )
