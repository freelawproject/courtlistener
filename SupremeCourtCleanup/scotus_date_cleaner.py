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
Process is roughly as follows:
For each row in the CSV:
    extract the case number from the row
    look up the case num in the DB
    for each hit in the DB:
        compute the difference ratio
        if any difference ratio > threshold:
            update the date for that case.
            write the row to updated_cases.csv
        else:
            write the row to punted_cases.csv
'''

import sys
sys.path.append('/var/www/court-listener/alert')

import settings
from django.core.management import setup_environ
setup_environ(settings)

import difflib, re
from alertSystem.models import Document, Citation


THRESHOLD = 0.75

f            = open("date_of_decisions.csv", 'r')
updated_file = open('updated_file.csv', 'w')
punt_file    = open('punted_cases.csv', 'w')

for line in f:
    caseNum = line.split("|")[0]
    docs = Document.objects.filter(citation__caseNumber = caseNum)

    diff_ratios = []
    for doc in docs:
        caseNameDB  = doc.citation.caseNameShort
        caseNameCSV = line.split("|")[1]

        # Remove 'United States' from all case names /before/ comparison.
        # Not doing so raises the opportunity for false positives.
        usa = re.compile(r'United States')
        caseNameDB  = usa.sub('', caseNameDB)
        caseNameCSV = usa.sub('', caseNameCSV)

        # compute the difference value
        diff = difflib.SequenceMatcher(None, caseNameDB, caseNameCSV).ratio()
        diff_ratios.append(diff)

    # Find the max value and its index
    if len(diff_ratios) > 0:
        max_ratio = max(diff_ratios)
        i = diff_ratios.index(max_ratio)
        if max_ratio >= THRESHOLD:
            # A hit!
            dateCSV = line.split('|')[4]
            doc = docs[i]
            doc.dateFiled = dateCSV
            doc.save()

            # Logging
            print "Updated document " + str(doc) + " with date: " + dateCSV
            updated_file.write(str(doc.documentUUID) + ":" + str(doc) + "|" + caseNameCSV + "|" + str(max_ratio)[0:7])
        else:
            # Not close enough. Punt.
            print "Ratio below threshold: " + str(max_ratio)
            punt_file.write("Punted: " + line)

    else:
        # No diff ratios generated.
        print "Punted line: " + line
        punt_file.write("Punted: " + line)

exit(0)
