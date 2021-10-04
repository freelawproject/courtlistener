from typing import Dict, Optional, Union, Tuple

from django.conf import settings


def has_been_pdfed(disclosure_url: str) -> Optional[str]:
    """Has file been PDFd from tiff and saved to AWS.

    :param disclosure_url: The URL of the first link (if there are more than
    one) of the source FD tiff(s)/PDF
    :return: Path to document or None
    """
    from cl.disclosures.models import FinancialDisclosure

    disclosures = FinancialDisclosure.objects.filter(
        download_filepath=disclosure_url
    )
    if disclosures.exists() and disclosures[0].filepath:
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
    from cl.disclosures.models import FinancialDisclosure

    if data["disclosure_type"] in ["jw", "single", "jef"]:
        url = data["url"]
    else:
        url = data["urls"][0]

    return FinancialDisclosure.objects.filter(
        download_filepath=url, has_been_extracted=True
    ).exists()


def make_disclosure_data(person) -> Tuple:
    """

    :param person:
    :return:
    """
    forms = (
        person.financial_disclosures.all()
        .order_by("-year")
        .values_list("year", "id")
    )
    years = []
    ids = []
    for yr, id in forms:
        years.append((str(yr)))
        ids.append(str(id))
    for x in set(years):
        number = 0
        for i in range(0, len(years)):
            if years[i] == x:
                number += 1
                if number >= 2:
                    years[i] += f" ({number})"
    return ",".join(years), ",".join(ids)
