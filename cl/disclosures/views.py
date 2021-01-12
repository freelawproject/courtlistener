import os

import magic
from django.conf import settings
from django.http import HttpResponse, HttpRequest
from django.shortcuts import render, get_object_or_404

from cl.disclosures.models import FinancialDisclosure
from cl.lib.bot_detector import is_bot
from cl.people_db.models import Person
from cl.people_db.views import make_title_str
from cl.stats.utils import tally_stat


def financial_disclosures_home(request: HttpRequest) -> HttpResponse:
    """The home page for financial disclosures

    This page shows:
     - A brief introduction to financial disclosure reports
     - A list of all the people we have reports for
     - A simple JS filter to find specific judges
    """
    people_with_disclosures = Person.objects.filter(
        financial_disclosures__isnull=False,
    ).distinct()
    disclosure_count = FinancialDisclosure.objects.all().count()
    people_count = people_with_disclosures.count()
    return render(
        request,
        "financial_disclosures_home.html",
        {
            "people": people_with_disclosures,
            "disclosure_count": disclosure_count,
            "people_count": people_count,
            "private": False,
        },
    )


def financial_disclosures_for_somebody(
    request: HttpRequest,
    pk: int,
    slug: str,
) -> HttpResponse:
    """Show the financial disclosures for a particular person"""
    person = get_object_or_404(Person, pk=pk)
    title = make_title_str(person)
    return render(
        request,
        "financial_disclosures_for_somebody.html",
        {"person": person, "title": title, "private": False},
    )


def financial_disclosures_fileserver(
    request: HttpRequest,
    pk: int,
    slug: str,
    filepath: str,
) -> HttpResponse:
    """Serve up the financial disclosure files."""
    response = HttpResponse()
    file_loc = os.path.join(settings.MEDIA_ROOT, filepath.encode())
    if settings.DEVELOPMENT:
        # X-Sendfile will only confuse you in a dev env.
        response.content = open(file_loc, "rb").read()
    else:
        response["X-Sendfile"] = file_loc
    filename = filepath.split("/")[-1]
    response["Content-Disposition"] = (
        'inline; filename="%s"' % filename.encode()
    )
    response["Content-Type"] = magic.from_file(file_loc, mime=True)
    if not is_bot(request):
        tally_stat("financial_reports.static_file.served")
    return response
