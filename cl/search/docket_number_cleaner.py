import re

from cl.lib.string_utils import normalize_dashes
from cl.search.models import Court

court_map = {
    "scotus": Court.FEDERAL_APPELLATE,
    "cadc": Court.FEDERAL_APPELLATE,
    "ca1": Court.FEDERAL_APPELLATE,
    "ca2": Court.FEDERAL_APPELLATE,
    "ca3": Court.FEDERAL_APPELLATE,
    "ca4": Court.FEDERAL_APPELLATE,
    "ca5": Court.FEDERAL_APPELLATE,
    "ca6": Court.FEDERAL_APPELLATE,
    "ca7": Court.FEDERAL_APPELLATE,
    "ca8": Court.FEDERAL_APPELLATE,
    "ca9": Court.FEDERAL_APPELLATE,
    "ca10": Court.FEDERAL_APPELLATE,
    "ca11": Court.FEDERAL_APPELLATE,
}

generic_patterns = {
    Court.FEDERAL_APPELLATE: [
        r"\d{1,2}-\d{1,6}-[a-zA-Z]{2}",  # e.g., 12-1234-ag, 12-1234-pr
        r"\d{1,2}-\d{1,6}[a-zA-Z]{1}",  # e.g., 12-1234P, 12-1234U
        r"\d{1,2}[a-zA-Z]{1}\d{1,6}",  # e.g., 12A1234, 12M1234
        r"[a-zA-Z]{1}-\d{1,6}",  # e.g., A-1234, D-1234
        r"\d{1,2}-\d{1,6}",  # e.g., 12-1234
        r"\d{1,6}",  # e.g., 1234
    ]
}


def get_clean_methods(court_type: str) -> tuple:
    """
    Returns cleaning methods for docket numbers based on the court type.

    :param court_type: The type of court, used to determine which cleaning methods to return.
    :return: A tuple containing two functions for cleaning docket numbers corresponding to the given court type.
               If the court type is not recognized, returns (None, None).
    """
    match court_type.lower():
        case "f":
            return prelim_clean_F, regex_clean_F
        case _:
            return None, None


def is_generic(s: str, court_map: str) -> bool:
    """
    Determines if the given string `s` matches any generic pattern associated with the specified `court_map`.

    :param s: The string to check against the generic patterns.
    :param court_map: The key used to retrieve the list of generic patterns from `generic_patterns`.
    :return: True if `s` matches any pattern for the given `court_map`, False otherwise.
    """
    patterns = generic_patterns.get(court_map, [])
    if any(re.fullmatch(p, s) for p in patterns):
        return True
    return False


def prelim_clean_F(s: str) -> str:
    """
    Cleans and normalizes federal appellate docket numbers.

    Steps:
    - Normalize dash characters.
    - Remove spaces around dashes.
    - Trim whitespace.
    - Remove trailing numbers after underscores.
    - Remove leading/trailing dashes and periods.
    - Remove common docket/case number prefixes.

    :param s: The input docket number string.
    :return: The cleaned and normalized docket number string.
    """
    s = normalize_dashes(s)
    s = s.strip()
    s = re.sub(r"\s*-\s*", "-", s)  # Remove spaces around dashes
    s = re.sub(r"_\d+$", "", s)  # Remove trailing numbers after underscores
    s = re.sub(r"^-+|-+$", "", s)  # Remove leading/trailing dashes
    s = re.sub(r"\.+$", "", s)  # Remove trailing periods
    s = re.sub(
        r"^(?:No\.?|Case No\.?|Docket No\.?|Docket|Case)\s+",
        "",
        s,
        flags=re.IGNORECASE,
    )  # Remove common prefixes
    return s


def regex_clean_F(s: str) -> str:
    """
    Cleans and normalizes federal appellate docket numbers from a given string.

    :param s: The input string containing raw federal appellate docket numbers.
    :return: A semicolon-separated string of cleaned and normalized docket numbers in uppercase.
    """
    # All patterns to match
    patterns = generic_patterns.get(Court.FEDERAL_APPELLATE, [])
    # Combine patterns into one regex
    combined_pattern = "|".join(patterns)
    candidates = re.findall(combined_pattern, s, flags=re.IGNORECASE)
    cleaned = []
    for c in candidates:
        # 1. Handle patterns with dash and suffix (e.g., 12-1234-ag)
        m = re.match(
            r"(\d{1,2})-(\d{1,6})-([a-zA-Z]{2})", c, flags=re.IGNORECASE
        )
        if m:
            yy, nnnn, suffix = m.groups()
            cleaned.append(f"{yy.zfill(2)}-{nnnn}-{suffix}")
            continue
        # 2. Handle patterns with dash and single-letter suffix (e.g., 12-1234P)
        m = re.match(
            r"(\d{1,2})-(\d{1,6})([a-zA-Z]{1})$", c, flags=re.IGNORECASE
        )
        if m:
            yy, nnnn, suffix = m.groups()
            cleaned.append(f"{yy.zfill(2)}-{nnnn}{suffix}")
            continue
        # 3. Handle patterns like 12-1234
        m = re.match(r"(\d{1,2})-(\d{1,6})$", c, flags=re.IGNORECASE)
        if m:
            yy, nnnn = m.groups()
            cleaned.append(f"{yy.zfill(2)}-{nnnn}")
            continue
        # 4. Handle patterns like 12A1234 or 12M1234
        m = re.match(
            r"(\d{1,2})([a-zA-Z]{1})(\d{1,6})", c, flags=re.IGNORECASE
        )
        if m:
            yy, letter, nnnn = m.groups()
            cleaned.append(f"{yy.zfill(2)}{letter}{nnnn}")
            continue
        # 5. Handle patterns like A-1234 or D-1234
        m = re.match(r"([a-zA-Z]{1})-(\d{1,6})", c, flags=re.IGNORECASE)
        if m:
            letter, nnnn = m.groups()
            cleaned.append(f"{letter}-{nnnn}")
            continue
        # 6. Handle just numbers
        m = re.match(r"^\d{1,6}$", c, flags=re.IGNORECASE)
        if m:
            cleaned.append(str(int(c)))
            continue

    cleaned = [s.upper() for s in cleaned]
    return "; ".join(cleaned)


def clean_docket_number_raw(
    docket_id: int, docket_number_raw: str, court_id: str
) -> tuple[str, int | None] | None:
    """
    Cleans a raw docket number string based on the court's specific cleaning logic and identifies those that need LLM cleaning.

    :param docket_id: The unique identifier for the docket.
    :param docket_number_raw: The raw docket number string to be cleaned.
    :param court_id: The identifier for the court, used to select cleaning logic.
    :return: A tuple containing the cleaned docket number and the docket_id for downstream LLM processing, if applicable. Or None.
    """
    court_type = court_map.get(court_id)

    if (
        not court_type
        or not docket_number_raw
        or not docket_number_raw.strip()
    ):
        return None

    prelim_func, regex_func = get_clean_methods(court_type)
    if not prelim_func:
        return None

    prelim_cleaned = prelim_func(docket_number_raw)
    if not is_generic(prelim_cleaned, court_type):
        return docket_number_raw, docket_id

    if not regex_func:
        return None

    docket_number = regex_func(prelim_cleaned)
    return docket_number, None
