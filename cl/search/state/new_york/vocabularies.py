"""Database choices for the vocabularies the Court-PASS scraper classifies into.

Juriscraper does the classifying
(`juriscraper.state.new_york.nycourts_gov.vocabularies`), but the enums we
store live here: the filing type, role, and document type vocabularies are
small enough to mirror, so what a stored code means is fixed by CourtListener
rather than by whichever Juriscraper happens to be installed.

Each mirror uses Juriscraper's member names and its published codes, so a
Juriscraper member maps onto its mirror by name -- `FilingType[member.name]`.
A name this module does not define is an upstream addition that has not been
mirrored yet; store `UNASSIGNED` for it, alongside the raw string, and add the
member here.

The issue category and subcategory vocabularies are the exception. There are
over 150 categories and roughly 1,700 subcategories, both drawn from the
Court's own index and both still growing, so their choices are generated from
Juriscraper's members instead. Their codes are published the same way and are
never renumbered or reused.

`UNKNOWN` and `UNASSIGNED` are reserved in every vocabulary and belong to no
member. Juriscraper reports both cases as `None` -- it has nothing to say --
and the raw string stored beside each of these fields is what tells them apart:

* `UNKNOWN`: the Court stated nothing. No FILINGS row named the filing, the
  filing type implies no role, the file name carried no readable document type.
* `UNASSIGNED`: the Court stated something the vocabulary does not cover, which
  is the signal that a member needs adding -- upstream, and then here.
"""

from django.db import models
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    CourtVocabulary,
    IssueCategory,
    IssueSubcategory,
)

__all__ = [
    "ISSUE_CATEGORY_CHOICES",
    "ISSUE_SUBCATEGORY_CHOICES",
    "UNASSIGNED",
    "UNKNOWN",
    "FilingDocType",
    "FilingRole",
    "FilingType",
]

UNKNOWN = 0
"""The Court stated nothing for this field."""

UNASSIGNED = 999
"""The Court stated something the vocabulary does not cover."""


class FilingType(models.IntegerChoices):
    """The filing types the FILINGS table on a docket page lists.

    A filing the scraper reconstructed from a document has none of these: no
    table row named it. Its role and document type are still classified.
    """

    UNKNOWN = 0, "Unknown"
    AD_APPELLANT_BRIEF = 1, "AD - Appellant Brief"
    AD_APPELLANT_REPLY_BRIEF = 2, "AD - Appellant Reply Brief"
    AD_APPENDIX = 3, "AD - Appendix"
    AD_RECORD = 4, "AD - Record"
    AD_RESPONDENT_APPENDIX = 5, "AD - Respondent Appendix"
    AD_RESPONDENT_BRIEF = 6, "AD - Respondent Brief"
    AMICUS_BRIEF = 7, "Amicus Brief"
    APPELLANT_APPENDIX = 8, "Appellant Appendix"
    APPELLANT_BRIEF = 9, "Appellant Brief"
    APPELLANT_COA_RECORD = 10, "Appellant COA Record"
    APPELLANT_RECORD = 11, "Appellant Record"
    APPELLANT_REPLY_BRIEF = 12, "Appellant Reply Brief"
    APPELLANT_RESPONSE_TO_AMICUS_BRIEF = (
        13,
        "Appellant Response to Amicus Brief",
    )
    APPELLANT_SSM_LETTER = 14, "Appellant SSM Letter"
    APPELLANT_RESPONDENT_BRIEF = 15, "Appellant-Respondent Brief"
    APPELLANT_RESPONDENT_REPLY_BRIEF = 16, "Appellant-Respondent Reply Brief"
    LAW_GUARDIAN_BRIEF = 17, "Law Guardian Brief"
    LAW_GUARDIAN_SSM_LETTER = 18, "Law Guardian SSM letter"
    PETITIONER_BRIEF = 19, "Petitioner Brief"
    PETITIONER_REPLY_BRIEF = 20, "Petitioner Reply Brief"
    PETITIONER_RESPONSE_REVIEW = 21, "Petitioner Response - Review"
    PETITIONER_RESPONSE_SUSPENSION = 22, "Petitioner Response - Suspension"
    PRO_SE_SUPPLEMENTAL_BRIEF = 23, "Pro Se Supplemental Brief"
    RECORD_ON_REVIEW = 24, "Record on Review"
    RESPONDENT_APPENDIX = 25, "Respondent Appendix"
    RESPONDENT_BRIEF = 26, "Respondent Brief"
    RESPONDENT_COA_RECORD = 27, "Respondent COA Record"
    RESPONDENT_RESPONSE_SUSPENSION = 28, "Respondent Response - Suspension"
    RESPONDENT_RESPONSE_TO_AMICUS_BRIEF = (
        29,
        "Respondent Response to Amicus Brief",
    )
    RESPONDENT_SSM_LETTER = 30, "Respondent SSM Letter"
    RESPONDENT_APPELLANT_BRIEF = 31, "Respondent-Appellant Brief"
    RESPONDENT_APPELLANT_REPLY_BRIEF = 32, "Respondent-Appellant Reply Brief"
    SCJC_DETERMINATION = 33, "SCJC Determination"
    SCJC_RESPONSE_SUSPENSION = 34, "SCJC Response - Suspension"
    UNASSIGNED = 999, "Unassigned"


class FilingRole(models.IntegerChoices):
    """The role of the party a filing belongs to.

    Read from the filing type, or from the role segment of a file name, where
    filers use a wide range of abbreviations for each of these.

    The three intervenor roles are not filing types the Court publishes; they
    are named in the ATTORNEY DETAILS section and abbreviated in file names.
    """

    UNKNOWN = 0, "Unknown"
    AMICUS = 1, "Amicus"
    APPELLANT = 2, "Appellant"
    APPELLANT_RESPONDENT = 3, "Appellant-Respondent"
    LAW_GUARDIAN = 4, "Law Guardian"
    PETITIONER = 5, "Petitioner"
    PRO_SE = 6, "Pro Se"
    RESPONDENT = 7, "Respondent"
    RESPONDENT_APPELLANT = 8, "Respondent-Appellant"
    SCJC = 9, "SCJC"
    INTERVENOR = 10, "Intervenor"
    INTERVENOR_APPELLANT = 11, "Intervenor-Appellant"
    INTERVENOR_RESPONDENT = 12, "Intervenor-Respondent"
    UNASSIGNED = 999, "Unassigned"


class FilingDocType(models.IntegerChoices):
    """The kind of document a filing consists of.

    Members with a code of 26 or higher are Juriscraper's rather than the
    Court's: the Court's published abbreviation list
    (https://www.nycourts.gov/ctapps/techspecs.htm) stops at the documents that
    carry a FILINGS-table filing type, and filers upload plenty it does not
    name. Nothing on a Court-PASS page equals one of them; they are reached
    only through Juriscraper's file-name patterns.

    Codes are in the order members were added, not alphabetically, because a
    published code never changes or gets reused.
    """

    UNKNOWN = 0, "Unknown"
    AD_APPENDIX = 1, "AD - Appendix"
    AD_BRIEF = 2, "AD - Brief"
    AD_RECORD = 3, "AD - Record"
    AD_REPLY_BRIEF = 4, "AD - Reply Brief"
    ADDENDUM = 5, "Addendum"
    AMICUS_BRIEF = 6, "Amicus Brief"
    APPENDIX = 7, "Appendix"
    BRIEF = 8, "Brief"
    BRIEF_AND_APPENDIX = 9, "Brief and Appendix"
    COMPENDIUM = 10, "Compendium"
    DECISION = 11, "Decision"
    EXHIBITS = 12, "Exhibits"
    MOTION = 13, "Motion"
    MOTION_FOR_LEAVE_TO_APPEAL = 14, "Motion for Leave to Appeal"
    OPPOSITION = 15, "Opposition"
    OPPOSITION_TO_MOTION_FOR_LEAVE_TO_APPEAL = (
        16,
        "Opposition to Motion for Leave to Appeal",
    )
    ORAL_ARGUMENT_TRANSCRIPT = 17, "Oral Argument Transcript"
    ORAL_ARGUMENT_WEBCAST = 18, "Oral Argument Webcast"
    RECORD = 19, "Record"
    REPLY_BRIEF = 20, "Reply Brief"
    RESPONSE_TO_AMICUS_BRIEF = 21, "Response to Amicus Brief"
    SSM_LETTER = 22, "SSM Letter"
    SSM_REPLY_LETTER = 23, "SSM Reply Letter"
    SUPPLEMENTAL_APPENDIX = 24, "Supplemental Appendix"
    SUPPLEMENTAL_BRIEF = 25, "Supplemental Brief"
    PRE_SENTENCE_REPORT = 26, "Pre-Sentence Report"
    AD_ORDER = 27, "AD - Order"
    AD_MOTION = 28, "AD - Motion"
    AFFIDAVIT_OF_SERVICE = 29, "Affidavit of Service"
    JURISDICTIONAL_RESPONSE = 30, "Jurisdictional Response"
    APPELLATE_TERM_BRIEF = 31, "Appellate Term - Brief"
    POST_ARGUMENT_BRIEF = 32, "Post-Argument Brief"
    HEARING_TRANSCRIPT = 33, "Hearing Transcript"
    UNASSIGNED = 999, "Unassigned"


def _choices(
    vocabulary: type[CourtVocabulary],
) -> list[tuple[int, str]]:
    """Django choices for one Juriscraper vocabulary, bracketed by the two
    reserved codes.

    Only for the vocabularies too large to mirror; see the module docstring.

    :param vocabulary: The Juriscraper vocabulary to generate choices from.
    :return: The choices, in the vocabulary's own order.
    """
    return [
        (UNKNOWN, "Unknown"),
        *((member.code, member.label) for member in vocabulary),
        (UNASSIGNED, "Unassigned"),
    ]


ISSUE_CATEGORY_CHOICES = _choices(IssueCategory)
ISSUE_SUBCATEGORY_CHOICES = _choices(IssueSubcategory)
