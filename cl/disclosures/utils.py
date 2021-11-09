from typing import Dict, Optional, Tuple, Union

from django.conf import settings

from cl.custom_filters.templatetags.text_filters import oxford_join
from cl.people_db.models import Person


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

    if data["disclosure_type"] in ["jw", "single", "jef", "pdf"]:
        url = data["url"]
    else:
        url = data["urls"][0]

    return FinancialDisclosure.objects.filter(
        download_filepath=url, has_been_extracted=True
    ).exists()


def make_disclosure_data(person: Person) -> Tuple[str, str]:
    """Make a CSV of the years and the IDs of somebody's disclosures

    :param person: The Person we're making data for
    :return: A tuple that can be passed to an HTML data attribute, and which
    contains a CSV of the years of the disclosures and their associated IDs.
    """
    forms = (
        person.financial_disclosures.all()
        .order_by("year")
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


def make_disclosure_year_range(person: Person) -> str:
    """Make a string representing the range of years a judge has disclosures

    For example, a judge with just one disclosure returns:
        "2000"

    A judge with just two disclosures returns:
        "2000 and 2010"

    A judge with three becomes:
        "2000, 2001, and 2003"

    A judge with four or more returns:
        "2000-2010"

    :param: person: The judge to inspect with their disclosures prefetched to
    the `disclosures` attribute.
    :returns: A string of the years of their disclosures
    """
    years = set()
    for fd in person.disclosures:
        years.add(fd.year)

    years = sorted(list(years))
    year_count = len(years)
    if year_count <= 3:
        # "2000", "2000 and 2001", "2000, 2001, and 2002"
        return oxford_join(years)
    else:
        return f"{years[0]}-{years[-1]}"
