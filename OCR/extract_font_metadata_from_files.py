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

from optparse import OptionParser
import operator
import os
import subprocess


DEVNULL = open('/dev/null', 'w')
def inspect(dir_name):
    """Get font information from PDFs.

    Recursively iterate over all the pdfs in a directory. For each found,
    extract the font information and throw it in a dictionary with a count. Sort
    the dict; print it out."""

    pdfs = []
    for r, d, f in os.walk(dir_name):
        for files in f:
            if files.endswith(".pdf"):
                 pdfs.append(os.path.join(r, files))
    fonts = {}
    for pdf in pdfs:
        # Extract the font information
        process = subprocess.Popen(["pdffonts", pdf], shell=False,
                                   stdout=subprocess.PIPE, stderr=DEVNULL)
        content, err = process.communicate()
        for line in content.split('\n')[2:-1]:
            font_with_plus = line.split(' ')[0]
            try:
                font = font_with_plus.split('+')[1]
            except IndexError:
                font = font_with_plus.split('+')[0]
            try:
                count = fonts[font]
                fonts[font] = count + 1
            except KeyError:
                fonts[font] = 1

    sorted_fonts = sorted(fonts.iteritems(), key=operator.itemgetter(1), reverse=True)
    for font_count in sorted_fonts:
        print '%s, %s' % font_count




def main():
    usage = "usage: %prog -d <path-to-pdfs>"
    parser = OptionParser(usage)
    parser.add_option('-d', '--directory', dest='dir_name',
                      metavar='DIRECTORY_NAME', help=('All PDFs under this ',
                              'location will be inspected. Use an absolute path.'))
    (options, args) = parser.parse_args()

    return inspect(options.dir_name)
    exit(0)

if __name__ == '__main__':
    main()
