# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.
'''
Process is as follows:
    For each row in the CSV:
        extract the case number from the row (caseNum = line.split("|")[0]
        Search for the case number using a query such as @westCite 107 676 @court scotus
        for each hit from this search:
            compute the difference ratio between the case name in the DB and that in the CSV
            if the max(difference_ratio) > THRESHOLD:
                update the date for that case.
                write the row to updated_cases.csv
            else:
                write the row to punted_cases.csv

Rationale for new method:
    This method uses search to find the case, which should be more efficient
    and accurate than using the DB. After using search, it uses the difference
    ratio to ensure that a correct ammendment is being made.

Spec/features:
    - verbose mode which prints to stdout
    - logs should be generated of the punted and completed files, including enough
      detail to revert a change.
    - simulate mode allows the user to generate the messages and logs without
      editing the DB
'''

import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alerts.models import Document, Citation
import datetime
import difflib
import string
from optparse import OptionParser
import re


def remove_words(phrase):
    # Removes words and punctuation that don't help the diff comparison.
    stop_words = 'a|an|and|as|at|but|by|en|etc|for|if|in|is|of|on|or|the|to|v\.?|via' +\
        '|vs\.?|united|states?|et|al|appellants?|defendants?|administrator|plaintiffs?|error' +\
        '|others|against|ex|parte|complainants?|original|claimants?|devisee' + \
        '|executrix|executor'
    stop_words_reg = re.compile(r'^(%s)$' % stop_words, re.IGNORECASE)

    # strips punctuation
    exclude = set(string.punctuation)
    phrase = ''.join(ch for ch in phrase if ch not in exclude)

    words = re.split('[\t ]', phrase)
    result = []
    for word in words:
        word = stop_words_reg.sub('', word)
        result.append(word)
    return ''.join(result)


def gen_diff_ratio(case_name_left, case_name_right):
    '''
    Genrates a difference between two strings, in this case case_names.
    Returns a value between 0 and 1. 0 means the strings are totally diffferent.
    1 means they are identical.
    '''
    # Remove common strings from all case names /before/ comparison.
    # Doing so lowers the opportunity for false positives.
    case_name_left = remove_words(case_name_left)
    case_name_right = remove_words(case_name_right)

    # compute the difference value
    diff = difflib.SequenceMatcher(None, case_name_left.strip(), case_name_right.strip()).ratio()

    return diff


def cleaner(simulate=False, verbose=False):
    f            = open("date_of_decisions.csv", 'r')
    updated_file = open('updated_file.log', 'w')
    punt_file    = open('punted_cases.log', 'w')

    line_num = 1
    for line in f:
        # extract the case number from the line in the CSV
        csv_case_name      = line.split("|")[1]
        csv_volume_num     = line.split("|")[2]
        csv_page_num       = line.split("|")[3]
        csv_date_published = line.split("|")[4]

        query = "@westCite (" + csv_volume_num + " << " + csv_page_num + ") @court scotus"

        # search for the case number using Sphinx
        queryset = Document.search.query(query)
        results = queryset.set_options(mode="SPH_MATCH_EXTENDED2")

        if results.count() == 0:
            # No hits for the doc. Log and punt it.
            print "Results: %d. Line number %d. Line contents: %s" % \
                (results.count(), line_num, line.strip())
            punt_file.write("Results: %d. Line number %d. Line contents %s\n" % \
                (results.count(), line_num, line.strip()))

        elif results.count() == 1:
            # One hit returned make sure it's above THRESHOLD. If so, fix it.
            HIGH_THRESHOLD = 0.3
            LOW_THRESHOLD  = 0.15
            db_case_name = str(results[0])
            diff = gen_diff_ratio(db_case_name, csv_case_name)
            if diff >= HIGH_THRESHOLD:
                # Update the date in the DB, this is a no brainer
                if not simulate:
                    splitDate = csv_date_published.split('-')
                    results[0].dateFiled = datetime.date(int(splitDate[0]),
                        int(splitDate[1]), int(splitDate[2]))
                    results[0].save()

                # Log as appropriate
                if verbose: print "Results: %d. Line number: %d. Diff_ratio: %f; Doc updated: %d: %s. Line contents: %s" % \
                    (results.count(), line_num, diff, results[0].documentUUID, results[0], line.strip())
                updated_file.write("Results: %d. Line number: %d. Diff_ratio: %f; Doc updated: %d: %s. Line contents: %s\n" % \
                    (results.count(), line_num, diff, results[0].documentUUID, results[0], line.strip()))

            elif (diff >= LOW_THRESHOLD) and (diff <= HIGH_THRESHOLD):
                # Ask the user if the change should be made.
                same = raw_input(str(results[0]) + "   ==   " + csv_case_name + " ?: ")
                if same == 'y':
                    # Update the date in the DB. Human says to.
                    if not simulate:
                        splitDate = csv_date_published.split('-')
                        results[0].dateFiled = datetime.date(int(splitDate[0]),
                            int(splitDate[1]), int(splitDate[2]))
                        results[0].save()

                    # Log as appropriate
                    if verbose: print "Results: %d. Line number: %d. Diff_ratio: %f; Doc updated: %d: %s. Line contents: %s" % \
                        (results.count(), line_num, diff, results[0].documentUUID, results[0], line.strip())
                    updated_file.write("Results: %d. Line number: %d. Diff_ratio: %f; Doc updated: %d: %s. Line contents: %s\n" % \
                        (results.count(), line_num, diff, results[0].documentUUID, results[0], line.strip()))
                else:
                    # Human says punt; therefore punt.
                    if verbose:
                        print "Results: %d. Line number %d punted by human. Diff_ratio: %f found on %d: %s; Line contents: %s" % \
                            (results.count(), line_num, diff, results[0].documentUUID, results[0], line.strip())
                    punt_file.write("Results: %d. Line number %d punted by human. Diff_ratio: %f found on %d: %s; Line contents: %s\n" % \
                        (results.count(), line_num, diff, results[0].documentUUID, results[0], line.strip()))

            else:
                # Below the threshold. Punt!
                if verbose:
                    print "Results: %d. Line number %d below threshold. Diff_ratio: %f found on %d: %s; Line contents: %s" % \
                        (results.count(), line_num, diff, results[0].documentUUID, results[0], line.strip())
                punt_file.write("Results: %d. Line number %d below threshold. Diff_ratio: %f found on %d: %s; Line contents: %s\n" % \
                    (results.count(), line_num, diff, results[0].documentUUID, results[0], line.strip()))

        elif results.count() > 1:
            # More than one hit. Find the best one using diff_lib
            THRESHOLD = 0.65

            diff_ratios = []
            for result in results:
                # Calculate its diff_ratio, and add it to an array
                db_case_name = str(result)
                diff = gen_diff_ratio(db_case_name, csv_case_name)
                diff_ratios.append(diff)

            # Find the max ratio, and grab the corresponding result
            max_ratio = max(diff_ratios)
            i = diff_ratios.index(max_ratio)
            if max_ratio >= THRESHOLD:
                # Update the date in the DB
                if not simulate:
                    splitDate = csv_date_published.split('-')
                    results[i].dateFiled = datetime.date(int(splitDate[0]),
                        int(splitDate[1]), int(splitDate[2]))
                    results[i].save()

                # Log as appropriate
                if verbose:
                    print "Results: %d. Line number: %d. Diff_ratio: %f; Doc updated: %d: %s. Line contents: %s" % \
                        (results.count(), line_num, max_ratio, results[i].documentUUID, results[i], line.strip())
                updated_file.write("Results: %d. Line number: %d. Diff_ratio: %f; Doc updated: %d: %s. Line contents: %s\n" % \
                    (results.count(), line_num, max_ratio, results[i].documentUUID, results[i], line.strip()))

            else:
                # Below the threshold. Punt!
                if verbose:
                    print "Results: %d. Line number %d below threshold. Diff_ratio: %f found on %d: %s; Line contents: %s" % \
                        (results.count(), line_num, max_ratio, results[i].documentUUID, results[i], line.strip())
                punt_file.write("Results: %d. Line number %d below threshold. Diff_ratio: %f found on %d: %s; Line contents: %s\n" % \
                    (results.count(), line_num, max_ratio, results[i].documentUUID, results[i], line.strip()))

        # increment the line number counter
        line_num += 1



def main():
    usage = "usage: %prog [--verbose] [---simulate]"
    parser = OptionParser(usage)
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose',
        default=False, help="Display log during execution")
    parser.add_option('-s', '--simulate', action="store_true",
        dest='simulate', default=False, help="Simulate the corrections without " + \
        "actually making them.")
    (options, args) = parser.parse_args()

    verbose = options.verbose
    simulate = options.simulate

    if simulate:
        print "*******************************************"
        print "* SIMULATE MODE - NO CHANGES WILL BE MADE *"
        print "*******************************************"

    return cleaner(simulate, verbose)
    exit(0)


if __name__ == '__main__':
    main()

