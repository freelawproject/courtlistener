# -*- coding: utf-8 -*-

import os
import fnmatch
from random import shuffle
import re
import traceback

from parse_opinions import parse_file
from populate_opinions import make_and_save


def do_many(dir_path, limit=None, random_order=True, status_interval=100):
    """Runs through a directory of the form /data/[state]/[sub]/.../[folders]/[.xml documents]. Parses each .xml
    document, instantiates the associated model object, and saves the object.
    Prints/logs status updates and tracebacks instead of raising exceptions.

    :param dir_path: The directory.
    :param limit: A limit on how many files to run through. If None, will run through all.
    :param random_order: If true, will run through the directories and files in relatively random order.
    :param status_interval: How often a status update will be given.
    """
    if limit:
        total = limit
    else:
        print "Getting an initial file count ..."
        total = 0
        for _, _, file_names in os.walk(dir_path):
            total += len(fnmatch.filter(file_names, '*.xml'))
    # go through the files, yielding parsed files and printing status updates as we go
    count = 0
    for root, dir_names, file_names in os.walk(dir_path):
        if random_order:
            shuffle(dir_names)
            shuffle(file_names)
        for file_name in fnmatch.filter(file_names, '*.xml'):
            path = os.path.join(root, file_name).replace('\\', '/')
            # grab the fallback text from the path if it's there
            court_fallback = ''
            matches = re.compile('data/([a-z_]+?/[a-z_]+?)/').findall(path)
            if matches:
                court_fallback = matches[0]
            # try to parse/save the case and print any exceptions with full tracebacks
            try:
                parsed = parse_file(path, court_fallback=court_fallback)
                make_and_save(parsed)
            except Exception as e:
                # print simple exception summaries for known problems
                if 'mismatched tag' in str(e):
                    print "Mismatched tag exception encountered in file '%s':%s" % (path, str(e).split(':', 1)[1])
                elif 'Failed to get a citation' in str(e):
                    print "Exception in file '%s': %s" % (path, str(e))
                else:
                    # otherwise, print generic traceback
                    print
                    print "Exception encountered in file '%s':" % path
                    print traceback.format_exc()
                    print
            # status update
            count += 1
            if count % status_interval == 0:
                print "Finished %s out of %s files." % (count, total)
            if count == limit:
                return


import django
django.setup()
do_many('/vagrant/flp/columbia_data/opinions/', random_order=True)