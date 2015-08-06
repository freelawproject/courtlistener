import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alert.settings")

import argparse
import hashlib
from juriscraper.lib.html_utils import get_clean_body_content
import datetime
from lxml.html import fromstring

import requests
from alert.corpus_importer.resource_org.helpers import (
    get_court_id, get_west_cite, get_docket_number, get_case_name_and_status,
    get_date_filed, get_case_body
)


from alert.lib.string_utils import anonymize
from alert.search.models import Document, Citation, Docket, Court


def import_resource_org_item(case_location):
    """Using the path to a case, import it, gathering all needed meta data.

    Path is any valid URI that the requests library can handle.
    """
    def get_file(location):
        if location.startswith('/'):
            with open(location) as f:
                r = requests.Session()
                r.content = f.read()
        else:
            r = requests.get(location)
        return fromstring(r.content), get_clean_body_content(r.content)

    # Get trees and text for the opinion itself and for the index page
    # that links to it. Each has useful data.
    case_tree, case_text = get_file(case_location)
    vol_location = case_location.rsplit('/', 1)[-2] + '/index.html'
    vol_tree, vol_text = get_file(vol_location)

    html, blocked = anonymize(get_case_body(case_tree))

    case_location_relative = case_location.rsplit('/', 1)[1]
    case_name, status = get_case_name_and_status(
        vol_tree, case_location_relative)
    cite = Citation(
        case_name=case_name,
        docket_number=get_docket_number(case_location),
        federal_cite_one=get_west_cite(vol_tree, case_location_relative),
    )
    docket = Docket(
        court=Court.objects.get(pk=get_court_id(case_tree)),
        case_name=case_name,
    )
    doc = Document(
        date_filed=get_date_filed(vol_tree, case_location_relative),
        source='R',
        sha1=hashlib.sha1(case_text).hexdigest(),
        citation=cite,
        docket=docket,
        download_url=case_location,
        html=html,
        precedential_status=status,
    )
    if blocked:
        doc.blocked = True
        docket.blocked = True
        doc.date_blocked = datetime.date.today()
        docket.date_blocked = datetime.date.today()

    cite.save()
    docket.save()
    doc.docket = docket
    doc.citation = cite
    doc.save()

    # Update the citation graph
    from alert.citations.tasks import update_document_by_id
    update_document_by_id(doc.pk)

    return doc


def main():
    parser = argparse.ArgumentParser(
        description=('A basic script to import a specific case. Brings the '
                     'item up to snuff with the other content in CL, but '
                     'doesn\'t do de-duping work or any of that other stuff. '
                     'Note that if two items have the same citation, we\'re '
                     'not handing that intelligently yet.')
    )
    parser.add_argument(
        '-l',
        '--location',
        required=True,
        help=('What is the location of the public.resource.org item you wish '
              'to import?\nValid locations could be:\n'
              '  /sources/Resource.org/data/F3/247/247.F3d.532.00-2881.html\n'
              '  https://bulk.resource.org/courts.gov/c/US/335/335.US.303.1.2.'
              'html')
    )
    args = parser.parse_args()

    _ = import_resource_org_item(args.location)


if __name__ == '__main__':
    main()
