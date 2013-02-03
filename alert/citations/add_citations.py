#!/usr/bin/env python
# encoding: utf-8

import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import sys
sys.path.append("/var/www/court-listener")

from alert.search.models import Document
from alert.lib.db_tools import queryset_generator
from celery.task.sets import TaskSet

# Celery requires imports like this. Disregard syntax error.
from citations.tasks import update_document

import time
from argparse import ArgumentParser

DEBUG = 2

def update_documents(documents):
    count = Document.objects.all().count()
    #count = 10
    processed_count = 0
    subtasks = []
    for doc in documents:
        subtasks.append(update_document.subtask((doc,)))
        processed_count += 1

        last_document = (count == processed_count)
        if (processed_count % 25 == 0) or last_document:
            # Every 25 documents, we send the subtasks off for processing
            # Poll to see when they're done.
            job = TaskSet(tasks=subtasks)
            result = job.apply_async()
            while not result.ready():
                time.sleep(0.25)

            # The jobs finished - clean things up for the next round
            subtasks = []

def main():
    parser = ArgumentParser()
    parser.add_argument('--doc_ids', type=int, nargs='+', default=[],
                        help='id(s) of one or more documents to update')
    parser.add_argument('--start_id', type=int, default=0,
                        help='start id for a range of documents to update')
    parser.add_argument('--end_id', type=int,
                        help='end id for a range of documents to update')
    args = parser.parse_args()

    if args.doc_ids and (args.start_id or args.end_id):
        parser.error("You cannot specify both a list and a range of ids.")

    if args.doc_ids:
        query = Document.objects.filter(pk__in=args.doc_ids)
    elif args.end_id:
        query = Document.objects.filter(pk__gte=args.start_id, pk__lte=args.end_id)
    else:
        query = Document.objects.filter(pk__gte=args.start_id)
    docs = queryset_generator(query)
    update_documents(docs)

if __name__ == '__main__':
    main()
