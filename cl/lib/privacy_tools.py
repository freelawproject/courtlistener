import re
from datetime import timedelta
from typing import Tuple

from django.utils.timezone import now

from cl.search.models import Court, Opinion


def set_blocked_status(opinion: Opinion, content: str, extension: str) -> None:
    """Figure out if the case should be blocked from search engines

    Use a number of rules to figure out if a case is better off out of search
    results. Also check the content of the document to see if it has SSNs or
    other sensitive data. If so, strip the sensitive content from those
    attributes of the opinion object. Do not save the object, that's up to the
    caller.

    For a discussion of the rules below, see:
    https://github.com/freelawproject/courtlistener/issues/691

    :param opinion: An opinion to check.
    :param content: The text of that opinion (usually from an extracted PDF).
    :param extension: The extension of the file, without the leading period.
    :return: None
    """

    def set_blocked(opinion: Opinion) -> None:
        opinion.cluster.blocked = True
        opinion.cluster.date_blocked = now()
        return None

    # Block if there is sensitive content in the document
    if extension in ["html", "wpd"]:
        opinion.html, found_ppi = anonymize(content)
    else:
        opinion.plain_text, found_ppi = anonymize(content)
    if found_ppi:
        set_blocked(opinion)
        return None

    oc = opinion.cluster
    court = opinion.cluster.docket.court
    lower_content = " ".join(content.lower().split())

    # Don't block things older than 30 years
    thirty_years_ago = now().date() - timedelta(days=30 * 365)
    from_last_thirty_years = oc.date_filed > thirty_years_ago
    if not from_last_thirty_years:
        return None
    #
    # Block based on rules and terms
    #
    if oc.precedential_status == "Unpublished":
        set_blocked(opinion)
        return None

    lower_state_court = court in Court.objects.filter(
        jurisdiction__in=[Court.STATE_TRIAL, Court.STATE_APPELLATE]
    )
    if lower_state_court and any(
        [
            "divorce" in lower_content,
            "minor" in lower_content and "child" in lower_content,
            "paternity" in lower_content,
            "wrongful termination" in lower_content,
        ]
    ):
        set_blocked(opinion)
        return None

    federal_district_court = court in Court.objects.filter(
        jurisdiction=Court.FEDERAL_DISTRICT
    )
    if federal_district_court and "asylum" in lower_content:
        set_blocked(opinion)
        return None

    not_appellate_court = court in Court.objects.exclude(
        jurisdiction__in=[
            Court.STATE_SUPREME,
            Court.FEDERAL_APPELLATE,
            Court.FEDERAL_BANKRUPTCY_PANEL,
        ]
    )
    if not_appellate_court and any(
        [
            "grams of cocaine" in lower_content,
            "grams of crack cocaine" in lower_content,
            "grams of marijuana" in lower_content,
        ]
    ):
        set_blocked(opinion)
        return None

    # fmt: off
    private_court = court in Court.objects.filter(
        pk__in=[
            # Military courts
            "afcca", "asbca", "armfor", "acca", "mc", "nmcca", "cavc", "bva",
            # Tax courts
            "tax", "bta", "ariztaxct", "indtc", "monttc", "njtaxct", "ortc",
            # Merit Systems Protection Board
            "mspb",
            # Workers' Comp, etc.
            "arkworkcompcom", "connworkcompcom", "tennworkcompcl",
            "tennworkcompapp"
        ]
    )
    # fmt: on
    if private_court:
        set_blocked(opinion)
        return None


def anonymize(s: str) -> Tuple[str, bool]:
    """Anonymizes private information.

    Converts SSNs, EINs, and A-Numbers to X's. Reports whether a modification
    was made, as a boolean.

    For more information about A-Numbers, see:
      https://www.uscis.gov/tools/glossary/number

    SSNs can be much more complicated than the implementation here. For
    details, see:
      https://rion.io/2013/09/10/validating-social-security-numbers-through-regular-expressions-2/
    """
    ssn_re = re.compile(r"\b(\d{3}-\d{2}-\d{4})\b", flags=re.VERBOSE)
    ein_re = re.compile(r"\b(\d{2}-\d{7})\b")
    a_number_re = re.compile(r"\b(A\d{8,9})\b")
    s, ssn_count = re.subn(ssn_re, r"XXX-XX-XXXX", s)
    s, ien_count = re.subn(ein_re, r"XX-XXXXXXX", s)
    s, a_number_count = re.subn(a_number_re, r"AXXXXXXXX", s)
    modified = bool(ssn_count + ien_count + a_number_count)
    return s, modified
