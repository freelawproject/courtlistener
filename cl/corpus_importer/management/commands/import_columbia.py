import os
import fnmatch
from random import shuffle
import re
import traceback
import logging
from glob import glob
from django.core.management.base import BaseCommand

from cl.corpus_importer.import_columbia.parse_opinions import parse_file
from cl.corpus_importer.import_columbia.populate_opinions import make_and_save
from cl.lib.import_lib import get_min_dates

class Command(BaseCommand):
    help = ('Parses the xml files in the specified directory into opinion objects that are saved.')

    def add_arguments(self, parser):
        parser.add_argument(
            'dir'
            ,nargs='+'
            ,type=str
            ,help='The directory that will be recursively searched for xml files.'
        )
        parser.add_argument(
            '--limit'
            ,type=int
            ,default=None
            ,help='Limit on how many files to run through. By default will run through all (or if `--random`, forever).'
        )
        parser.add_argument(
            '--random'
            ,action='store_true'
            ,default=False
            ,help='If set, will run through the directories and files in random order.'
        )
        parser.add_argument(
            '--status'
            ,type=int
            ,default=100
            ,help='How often a status update will be given. By default, every 100 files.'
        )
        parser.add_argument(
            '--log'
            ,type=str
            ,default=None
            ,help='The file to which file paths that raise exceptions will be logged.'
        )
        parser.add_argument(
            '--newcases'
            ,action='store_true'
            ,default=False
            ,help='If set, will skip court-years that already have data.'
        )
        parser.add_argument(
            '--skipdupes'
            ,action='store_true'
            ,default=False
            ,help='If set, will skip duplicates.'
        )
        parser.add_argument(
            '--startfolder'
            ,type=str
            ,default=None
            ,help='The folder (state name) to start on.'
        )
        parser.add_argument(
            '--startfile'
            ,type=str
            ,default=None
            ,help='The file name to start on (if resuming).'
        )        
    def handle(self, *args, **options):
        do_many(options['dir'][0], options['limit'], options['random'], options['status'], options['log']
                , options['newcases'], options['skipdupes'], options['startfolder'])


def do_many(dir_path, limit=None, random_order=False, status_interval=100, log_file=None,
                newcases=False, skipdupes=False, startfolder=None, startfile=None):
    """Runs through a directory of the form /data/[state]/[sub]/.../[folders]/[.xml documents]. Parses each .xml
    document, instantiates the associated model object, and saves the object.
    Prints/logs status updates and tracebacks instead of raising exceptions.

    :param dir_path: The directory.
    :param limit: A limit on how many files to run through. If None, will run through all (or if random order, forever).
    :param random_order: If true, will run through the directories and files in random order.
    :param status_interval: How often a status update will be given.
    :param log_file: If not None, file paths that raise Exceptions will be logged to this file.
    :param newcases: If true, skip court-years that already have data.
    :param skipdupes: If true, skip duplicates.
    :param startfolder: If not None, start on startfolder
    :param startfile: If not None, start on this file (for resuming)
    """
    if limit:
        total = limit
    elif not random_order:
        print ("Getting an initial file count ...")
        print
        total = 0
        for _, _, file_names in os.walk(dir_path):
            total += len(fnmatch.filter(file_names, '*.xml'))
    else:
        total = None
    log = None
    if log_file:
        print ("Logging problematic file paths to '%s' ..." % log_file)
        print
        log = logging.getLogger(__name__)
        log.setLevel(logging.INFO)
        log.addHandler(logging.FileHandler(log_file))
    # go through the files, yielding parsed files and printing status updates as we go
    folders = glob(dir_path+'/*')
    folders.sort()
    count = 0
    
    # get earliest dates for each court
    if newcases:
        print('Only new cases: getting earliest dates by court.')
        min_dates = get_min_dates()
    
    # start/resume functionality
    if startfolder is not None:
        skipfolder = True
    else:
        skipfolder = False
    if startfile is not None:
        skipfile = True
    else:
        skipfile = False
        
    for folder in folders:
        if skipfolder:
            if startfolder is not None:
                checkfolder = folder.split('/')[-1]
                if checkfolder == startfolder:
                    skipfolder = False
                else:
                    continue        
        print(folder)
            
        for path in file_generator(folder, random_order, limit):
            
            if skipfile:
                if startfile is not None:
                    checkfile = path.split('/')[-1]
                    if checkfile == startfile:
                        skipfile = False
                    else:
                        continue        
        print(path)
            
            # grab the fallback text from the path if it's there
            court_fallback = ''
            matches = re.compile('data/([a-z_]+?/[a-z_]+?)/').findall(path)
            if matches:
                court_fallback = matches[0]
            # skip cases in 'misc*' folders -- they are relatively different than the other cases, so we'll deal with them
            #  later
            if 'miscellaneous_court_opinions' not in path:
                # try to parse/save the case and print any exceptions with full tracebacks                
                try:
                    parsed = parse_file(path, court_fallback=court_fallback)
                    make_and_save(parsed,skipdupes, min_dates)
                except Exception as e:
                    # log the file name
                    if log:
                        log.info(path)
                    # print simple exception summaries for known problems
                    known = [
                        'mismatched tag', 'Failed to get a citation', 'Failed to find a court ID',
                        'null value in column "date_filed"', 'duplicate(s)'
                    ]
                    if any(k in str(e) for k in known):
                        print
                        print "Known exception in file '%s':" % path
                        print str(e)
                        print
                    else:
                        # otherwise, print generic traceback
                        print
                        print "Unknown exception in file '%s':" % path
                        print traceback.format_exc()
                        print
            # status update
            count += 1
            if count % status_interval == 0:
                print
                if total:
                    print "Finished %s out of %s files." % (count, total)
                else:
                    print "Finished %s files." % count
                print


def file_generator(dir_path, random_order=False, limit=None):
    """Generates full file paths to all xml files in `dir_path`.

    :param dir_path: The path to get files from.
    :param random_order: If True, will generate file names randomly (possibly with repeats) and will never stop
        generating file names.
    :param limit: If not None, will limit the number of files generated to this integer.
    """
    count = 0
    if not random_order:
        for root, dir_names, file_names in os.walk(dir_path):
            file_names.sort()
            for file_name in fnmatch.filter(file_names, '*.xml'):
                yield os.path.join(root, file_name).replace('\\', '/')
                count += 1
                if count == limit:
                    return
    else:        
        for root, dir_names, file_names in os.walk(dir_path):
            shuffle(dir_names)
            names = fnmatch.filter(file_names, '*.xml')
            if names:
                shuffle(names)
                yield os.path.join(root, names[0]).replace('\\', '/')
                break
        count += 1
        if count == limit:
            return
