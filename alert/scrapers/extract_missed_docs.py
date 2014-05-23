#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import datetime
import os
import sys
import time
import traceback

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from alert.search.models import Court
from alert.search.models import Document
from celery.task.sets import subtask
from django.core.exceptions import ObjectDoesNotExist
from scrapers.tasks import extract_doc_content, extract_by_ocr


def extract_all_docs(docs):
    num_docs = docs.count()
    if num_docs == 0:
        print "Nothing to parse for this court."
    else:
        print "%s documents in this court." % (num_docs,)
        for doc in docs:
            extract_doc_content.delay(doc.pk, callback=subtask(extract_by_ocr))


def main():
    parser = argparse.ArgumentParser(description="Extract document content from cases.")
    parser.add_argument('-c', '--court', dest='court_id', metavar="COURTID",
                        help="The court to extract. Use 'all' to extract all courts.")
    parser.add_argument('-d', '--document', dest='docs', metavar="DOC", nargs='+',
                        help="The document IDs to extract.")
    parser.add_argument('-t', '--time', dest='filter_time', metavar='DATE-TIME',
                        help=("Take action for all documents newer than this time."
                              " Format as follows: YYYY-MM-DD HH:MM:SS or"
                              " YYYY-MM-DD"))
    options = parser.parse_args()

    court = options.court_id

    if options.docs is not None:
        for doc in options.docs:
            try:
                doc = Document.objects.filter(pk=doc)
                extract_all_docs(doc)
            except ObjectDoesNotExist:
                print "The following document was not found: %s" % doc
            except Exception:
                print '*****Uncaught error parsing court*****\n"' + traceback.format_exc() + "\n\n"

    else:
        filter_time = options.filter_time
        if filter_time:
            try:
                # Parse the date string into a datetime object
                filter_time = datetime.datetime(*time.strptime(options.filter_time, "%Y-%m-%d %H:%M:%S")[0:6])
            except ValueError:
                try:
                    filter_time = datetime.datetime(*time.strptime(options.filter_time, "%Y-%m-%d")[0:5])
                except ValueError:
                    parser.error("Unable to parse time. Please use format: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD")
        else:
            # Without a time filter, this query is locking, taking a long time.
            parser.error('Time is a required argument.')

        if court == 'all':
            # get the court IDs from models.py
            courts = Court.objects.filter(in_use=True).values_list('pk', flat=True)
            for court in courts:
                print "NOW PARSING COURT: %s" % court
                # This catches all exceptions regardless of their trigger, so
                # if one court dies, the next isn't affected.
                try:
                    docs = Document.objects.filter(plain_text="", html="",
                                                   court__pk=court, source="C",
                                                   date_filed__gte=filter_time)
                    extract_all_docs(docs)
                except Exception:
                    print '*****Uncaught error parsing court*****\n"' + traceback.format_exc() + "\n\n"
        else:
            # We just do the court requested
            print "NOW PARSING COURT: %s" % court
            docs = Document.objects.filter(plain_text="", html="",
                                           court__pk=court, source="M",
                                           date_filed__gte=filter_time)
            extract_all_docs(docs)

    exit(0)

if __name__ == '__main__':
    main()
