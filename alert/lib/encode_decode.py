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
# alphabet used for url encoding and decoding. Omits some letters, like O0l1.

ALPHABET = "123456789abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"

def ascii_to_num(string, alphabet=ALPHABET):
    from django.http import Http404
    """Decode an ascii string back to the number it represents

    `string`: The string to decode
    """

    base = len(alphabet)
    strlen = len(string)
    num = 0
    i = 0
    try:
        for char in string:
            power = (strlen - (i + 1))
            num += alphabet.index(char) * (base ** power)
            i += 1
    except ValueError:
        # happens if letters like l, 1, o, 0 are used.
        raise Http404

    return num


def num_to_ascii(num, alphabet=ALPHABET):
    """Encode a number in Base X

    `num`: The number to encode
    """
    if (num <= 0):
        return alphabet[0]
    arr = []
    base = len(alphabet)
    while num:
        rem = num % base
        num = num // base
        arr.append(alphabet[rem])
    arr.reverse()
    return ''.join(arr)
