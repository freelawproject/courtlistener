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
        if (processed_count % 20 == 0) or last_document:
            # Every 1000 documents, we send the subtasks off for processing
            job = TaskSet(tasks=subtasks)
            result = job.apply_async()
            while not result.ready():
                time.sleep(0.25)

            # The jobs finished - clean things up for the next round
            subtasks = []

def update_documents_by_id(id_list):
    docs = Document.objects.filter(pk__in=id_list)
    update_documents(docs)

def main():
    docs = queryset_generator(Document.objects.all(), start=1000)
    #docs = Document.objects.all()[:10]
    update_documents(docs)

if __name__ == '__main__':
    main()
