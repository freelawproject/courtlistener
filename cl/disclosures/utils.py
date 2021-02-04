from typing import Dict, Optional, Union

from django.conf import settings

from cl.disclosures.models import FinancialDisclosure


def has_been_pdfed(disclosure_url: str) -> Optional[str]:
    """Has file been PDFd from tiff and saved to AWS.

    :param disclosure_url: The URL of the first link (if there are more than
    one) of the source FD tiff(s)/PDF
    :return: Path to document or None
    """

    disclosures = FinancialDisclosure.objects.filter(
        download_filepath=disclosure_url
    )
    if disclosures.exists():
        return (
            f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/"
            f"{disclosures[0].filepath}"
        )


def has_been_extracted(data: Dict[str, Union[str, int, list]]) -> bool:
    """Has PDF been extracted

    Method added to skip tiff to pdf conversion if
    document has already been converted and saved but
    not yet extracted.

    :param data: File data
    :return: Whether document has been extracted
    """

    if data["disclosure_type"] == "jw" or data["disclosure_type"] == "single":
        url = data["url"]
    else:
        url = data["urls"][0]

    return FinancialDisclosure.objects.filter(
        download_filepath=url, has_been_extracted=True
    ).exists()
