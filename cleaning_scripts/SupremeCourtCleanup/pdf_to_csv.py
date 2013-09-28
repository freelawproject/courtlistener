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
"""
This file converts the supreme court doc into something useful, namely a
CSV file....in theory.
"""
import re
import time
from datetime import date

DEBUG = True

f = open("date_of_decisions.txt")
out = open('date_of_decisions.csv', "w")

volume_num = re.compile(r'^ +(\d{1,3})')
page_and_case   = re.compile(r'(^\d+)[n ](.*?)\.\.')
date_regex = re.compile(r'.*?\[?([^.]*\.[^.]+)$')
month_regex = re.compile(r'.*([a-zA-Z]{3}).*')
day_regex = re.compile(r'.*?(\d{2}).*')
year_regex = re.compile(r'.*(\d{4})$')

for line in f:
    mg_vol     = re.search(volume_num, line)
    if mg_vol:
        # it's a header for a volume, parse out the volume number
        volume = mg_vol.group(0).strip()
        if DEBUG: print "****\nVolume: " + volume + "\n****"

    mg_pg_case = re.match(page_and_case, line)
    mg_date    = re.match(date_regex, line)
    if mg_pg_case and mg_date:
        # Next: page numbers
        page = mg_pg_case.group(1).strip()
        if DEBUG: print "Page: " + page

        # Next: Case name
        case = mg_pg_case.group(2).strip()
        if DEBUG: print "Case: " + case

        # Next: Date
        case_date = mg_date.group(1).strip().strip('[]#*.').strip()

        # Format the case date neatly.
        if 'term' not in case_date:
            if volume == '20' and page == '35':
                case_date = "Feb. 14, 1822"
            if volume == '34' and page == '711':
                case_date = "Mar. 17, 1835"
            if volume == '41' and page == '367':
                case_date = "Feb. 9, 1842"
            if volume == '66' and page == '96':
                case_date = 'Jan. 6, 1862'
            if volume == '69' and page == '649':
                case_date = 'Apr. 4, 1864'
            if volume == '105' and page == '414':
                case_date = 'Apr. 10, 1882'

            year = re.match(year_regex, case_date).group(1)
            month = re.match(month_regex, case_date).group(1)
            day = re.match(day_regex, case_date).group(1)
            if DEBUG:
                print "Date: " + case_date
            case_date = str(date(*time.strptime(month + ". " + day + ", " + year, '%b. %d, %Y')[:3]))

        # specific cleanups
        if volume == 59 and page == 19:
            case = "Kissell v. Board of President and Directors of St.Louis"
        if volume == 91 and page == 127:
            case = "Baltimore & Potomac R.Co. v. Trustees of Sixth Presb."
        if volume == 93 and page == 595:
            case = 'West Wisc. R. Co. v. Bd. of Superv. Trempealeau Cty'
        if volume == 107 and page == 98:
            case = 'Green Bay & Minnesota R.Co. v. Union Steamboat Co.'

    try:
        contents = [volume + " U.S. " + page, case, volume, page, case_date]
        csv_line = "|".join(contents) + '\n'
        out.write(csv_line)
        del page, case, case_date
    except NameError:
        pass

exit(0)
