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

from django.utils.encoding import smart_str


def fix_mojibake(text):
    '''Given corrupt text from pdffactory, converts it to sane text.'''

    letter_map = {
                  u'¿':'a',
                  u'¾':'b',
                  u'½':'c',
                  u'¼':'d',
                  u'»':'e',
                  u'º':'f',
                  u'¹':'g',
                  u'¸':'h',
                  u'·':'i',
                  u'¶':'j',
                  u'μ':'k',
                  u'´':'l',
                  u'³':'m',
                  u'²':'n',
                  u'±':'o',
                  u'°':'p',
                  u'¯':'q',
                  u'®':'r',
                  u'-':'s',
                  u'¬':'t',
                  u'«':'u',
                  u'ª':'v',
                  u'©':'w',
                  u'¨':'x',
                  u'§':'y',
                  u'¦':'z',
                  u'ß':'A',
                  u'Þ':'B',
                  u'Ý':'C',
                  u'Ü':'D',
                  u'Û':'E',
                  u'Ú':'F',
                  u'Ù':'G',
                  u'Ø':'H',
                  u'×':'I',
                  u'Ö':'J',
                  u'Õ':'K',
                  u'Ô':'L',
                  u'Ó':'M',
                  u'Ò':'N',
                  u'Ñ':'O',
                  u'Ð':'P',
                  u'':'Q', # Missing
                  u'Î':'R',
                  u'Í':'S',
                  u'Ì':'T',
                  u'Ë':'U',
                  u'Ê':'V',
                  u'É':'W',
                  u'':'X', # Missing
                  u'Ç':'Y',
                  u'Æ':'Z',
                  u'ð':'0',
                  u'ï':'1',
                  u'î':'2',
                  u'í':'3',
                  u'ì':'4',
                  u'ë':'5',
                  u'ê':'6',
                  u'é':'7',
                  u'è':'8',
                  u'ç':'9',
                  u'ò':'.',
                  u'ô':',',
                  u'æ':':',
                  u'å':';',
                  u'Ž':"'",
                  u'•':"'",
                  u'•':"'", # s/b double quote, but identical to single.
                  u'Œ':"'", # s/b double quote, but identical to single.
                  u'ó':'-', # dash
                  u'Š':'-', # n-dash
                  u'‰':'--', # em-dash
                  u'ú':'&',
                  u'ö':'*',
                  u'ñ':'/',
                  u'÷':')',
                  u'ø':'(',
                  u'Å':'[',
                  u'Ã':']',
                  u'‹':'•',
                 }

    plaintext = ''
    for letter in text:
        try:
            plaintext += letter_map[letter]
        except KeyError:
            try:
                plaintext += smart_str(letter)
            except UnicodeEncodeError:
                continue

    return plaintext
