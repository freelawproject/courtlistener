import os
import sys
sys.path.append(os.getenv('CL_INSTALL_ROOT', '/var/www/courtlistener'))

from alert import settings
from django.core.management import setup_environ

setup_environ(settings)

from alert.search.models import Document
from difflib import Differ
from optparse import OptionParser
import datetime
import re
import urllib2


def toggle_blocked_status(url, block_or_unblock, simulate, verbose):
    """Toggles the blocked status of all documents that have a download_URL
    equal to the input value.
    """
    # Parse out the stuff we don't want.
    url = 'http://bulk.resource.org' + re.sub('(\+|-) Disallow: ', '', url)
    url = url.strip()

    docs = Document.objects.filter(download_URL=url)
    if verbose:
        print "Searched for: %s" % (url)
        print "Found %s cases." % (len(docs))
    for doc in docs:
        if block_or_unblock == 'block':
            if verbose:
                print "Blocking: %s" % (url)
            doc.blocked = True
            doc.date_blocked = datetime.date.today()
        elif block_or_unblock == "unblock":
            if verbose:
                print "Unblocking: %s" % (url)
            doc.blocked = False
            doc.date_blocked = None
        if not simulate:
            doc.save()


def compare_files(new_file_content, old_file_content, verbose):
    """Compare the values of the files and return a list containing what's the
    same, different or changed."""
    d = Differ()

    results = list(d.compare(old_file_content, new_file_content))

    if verbose:
        print "Differences %s" % (results)
    return results


def get_file_from_resource_org():
    """Gets the file from resource.org, and returns it to the calling function.
    """
    try:
        new_file_content = urllib2.urlopen('http://bulk.resource.org/robots.txt').readlines()
    except urllib2.HTTPError:
        print "Curses. Downloading error."
        exit(1)

    return new_file_content


def update_db_from_resource_org(simulate, verbose):
    """Updates the DB with the latest robots.txt file at resource.org

    Gets the latest file and finds any new or removed lines within it. Documents
    are then updated with these findings by toggling their 'block' flag.
    """
    # Set up our working directory
    os.chdir(os.path.join(settings.INSTALL_ROOT, 'alert'))

    # Get the latest file
    new_file_content = get_file_from_resource_org()

    # Get the cached local file
    try:
        old_file = open('robots/cached_file.txt', 'r')
        old_file_content = old_file.readlines()
        old_file.close()
    except IOError:
        old_file_content = ''

    # Compare the latest file to the one saved locally.
    differences = compare_files(new_file_content, old_file_content, False)

    # For each line, identify whether it's new or removed.
    for line in differences:
        # If new, toggle the blocked flag to true.
        if line.startswith('+ Disallow'):
            toggle_blocked_status(line, 'block', simulate, verbose)
        # If removed, toggle the blocked flag to false.
        elif line.startswith('- Disallow'):
            toggle_blocked_status(line, 'unblock', simulate, verbose)
        else:
            # These are lines with comments or that we don't care about.
            pass

    # Finally, write the new file to disk so that it may become the old file
    # next time.
    old_file = open('robots/cached_file.txt', 'w')
    for line in new_file_content:
        old_file.write(line)
    old_file.close()


def main():
    usage = "usage: %prog [--verbose] [--simulate]"
    parser = OptionParser(usage)
    parser.add_option('-u', '--update', action='store_true',
                      dest='update', default=False, help="Update the DB with any new " + \
                                                         "entries at bulk.resource.org/robots.txt")
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose',
                      default=False, help="Display variable values during execution")
    parser.add_option('-s', '--simulate', action="store_true",
                      dest='simulate', default=False, help="Simulate updating the " + \
                                                           "database")
    (options, args) = parser.parse_args()

    verbose = options.verbose
    simulate = options.simulate
    update = options.update

    if update:
        update_db_from_resource_org(simulate, verbose)
    if simulate and verbose:
        print "***********************"
        print "* NO DATA WAS CHANGED *"
        print "***********************"

    exit(0)


if __name__ == '__main__':
    main()
