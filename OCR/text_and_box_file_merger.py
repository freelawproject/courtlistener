# -*- coding: utf-8 -*-

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
import codecs
import itertools


def merge_file(text_file, box_file):
    '''Merges a text file with a box file so it doesn't have to be done manually.

    We take each char from the text file, and each line from the box file, and
    simply line them up. If there are more lines from either, they'll end up
    at the end.'''

    # Get the text from the text file and put it in an array
    text = codecs.open(text_file, 'r', 'utf-8').read()

    # Get the content from the box file, and put each line in an array
    box_file = codecs.open(box_file, 'r', 'utf-8')
    out_file = codecs.open('out_file.txt', 'w+', 'utf-8')

    # Iterate over each char from the text file, and put it in each line from
    # the box file. If there are any more chars, put them down, one per line.
    # If there are any more lines from the box file, put them down too.
    for c,line in itertools.izip_longest(text, box_file):
        if c == ' ':
            continue
        if (c is not None) and (line is not None):
            try:
                out_file.write(c + line[1:])
            except UnicodeDecodeError:
                out_file.write(' ' + line[1:])
        elif c is not None:
            out_file.write(c + '\n')
        elif line is not None:
            out_file.write(line[1:])

def main():
    usage = "usage: %prog -d <path-to-pdfs>"
    parser = OptionParser(usage)
    parser.add_option('-t', '--textfile', dest='text_file',
                      metavar='TEXT_FILE', help=('This file should contain',
                      'the text that you used to make your training image.'))
    parser.add_option('-b', '--boxfile', dest='box_file',
                      metavar='BOX_FILE', help=('This file should contain',
                      'a box file as generated by Tesseract.'))
    (options, args) = parser.parse_args()

    return merge_file(options.text_file, options.box_file)
    exit(0)

if __name__ == '__main__':
    main()
