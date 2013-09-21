from alert.search.models import Court
from alert.search.models import Document
from alert.lib.db_tools import queryset_generator_by_date
from alert.lib.dump_lib import make_dump_file
from alert.lib.dump_lib import get_date_range
from alert.lib.filesize import size
from alert.settings import DUMP_DIR

from django.http import HttpResponseBadRequest
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext

import os
from datetime import date
from alert.stats import tally_stat


def dump_index(request):
    """Shows an index page for the dumps."""
    court_count = Court.objects.exclude(jurisdiction='T').count()  # Non-testing courts
    try:
        dump_size = size(os.path.getsize(os.path.join(DUMP_DIR, 'all.xml.gz')))
    except os.error:
        # Happens when the file is unaccessible or doesn't exist. An estimate.
        dump_size = '3.2GB'
    return render_to_response('dumps/dumps.html',
                              {'court_count': court_count,
                               'dump_size': dump_size,
                               'private': False},
                              RequestContext(request))


def serve_or_gen_dump(request, court, year=None, month=None, day=None):
    """Serves the dump file to the user, generating it if needed."""
    if year is None:
        if court != 'all':
            # Sanity check
            return HttpResponseBadRequest('<h2>Error 400: Complete dumps are '
                'not available for individual courts. Try using "all" for '
                'your court ID instead.</h2>')
        else:
            # Serve the dump for all cases.
            tally_stat('bulk_data.served.all')
            return HttpResponseRedirect('/dumps/all.xml.gz')

    else:
        # Date-based dump
        start_date, end_date, annual, monthly, daily = get_date_range(year, month, day)

        # Ensure that it's a valid request.
        today = date.today()
        if (today < end_date) and (today < start_date):
            # It's the future. They fail.
            return HttpResponseBadRequest('<h2>Error 400: Requested date is '
                'in the future. Please try again then.</h2>')
        elif today <= end_date:
            # Some of the data is in the past, some could be in the future.
            return HttpResponseBadRequest('<h2>Error 400: Requested date is '
                'partially in the future. Please try again then.</h2>')

    filename = court + '.xml'
    if daily:
        filepath = os.path.join(year, month, day)
    elif monthly:
        filepath = os.path.join(year, month)
    elif annual:
        filepath = os.path.join(year)

    path_from_root = os.path.join(DUMP_DIR, filepath)

    # See if we already have it on disk.
    try:
        _ = open(os.path.join(path_from_root, filename + '.gz'), 'rb')
        tally_stat('bulk_data.served.by_date')
        return HttpResponseRedirect(os.path.join('/dumps', filepath, filename + '.gz'))
    except IOError:
        # Time-based dump
        if court == 'all':
            # dump everything; disable default sorting
            qs = Document.objects.all().order_by()
        else:
            # dump just the requested court; disable default sorting
            qs = Document.objects.filter(court=court).order_by()

        # check if there are any documents at all
        dump_has_docs = qs.filter(date_filed__gte=start_date,
                                  date_filed__lte=end_date).exists()
        if dump_has_docs:
            docs_to_dump = queryset_generator_by_date(qs,
                                                      'date_filed',
                                                      start_date,
                                                      end_date)

            make_dump_file(docs_to_dump, path_from_root, filename)
        else:
            print "Bad request!"
            return HttpResponseBadRequest('<h2>Error 400: We do not have any data for this time period.</h2>',
                                          status=404)

        tally_stat('bulk_data.served.by_date')
        return HttpResponseRedirect('%s.gz' % os.path.join('/dumps', filepath, filename))
