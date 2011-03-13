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


"""
This file demonstrates two different styles of tests (one doctest and one
unittest). These will both pass when you run "manage.py test".

Replace these with more appropriate tests for your application.
"""

from django.test import TestCase
from lib.string_utils import harmonize

class SimpleTest(TestCase):
    def test_basic_addition(self):
        """
        Tests that 1 + 1 always equals 2.
        """
        self.failUnlessEqual(1 + 1, 2)

__test__ = {"doctest": """
>>> harmonize('U.S.A. v. Lissner')
'United States v. Lissner'
>>> harmonize('U.S. v. Lissner')
'United States v. Lissner'
>>> harmonize('United States v. Lissner')
'United States v. Lissner'
>>> harmonize('Usa v. Lissner')
'United States v. Lissner'
>>> harmonize('USA v. Lissner')
'United States v. Lissner'
>>> harmonize('United States of America v. Lissner')
'United States v. Lissner'
>>> harmonize('Lissner v. United States of America')
'Lissner v. United States'
>>> harmonize('V.Vivack and Associates v. US')
'V.Vivack and Associates v. United States'
>>> harmonize('v.v. Hendricks & Sons v. James v. Smith')
'v.v. Hendricks & Sons v. James v. Smith'
>>> harmonize('v.v. Hendricks v. James V. Smith v. US')
'v.v. Hendricks v. James V. Smith v. United States'
>>> harmonize('U.S.A. v. Mr. v.')
'United States v. Mr. v.'
>>> harmonize('U.S.S. v. Lissner')
'U.S.S. v. Lissner'
>>> harmonize('USC v. Lissner')
'USC v. Lissner'
>>> harmonize('U.S.C. v. Lissner')
'U.S.C. v. Lissner'
>>> harmonize('U.S. Steel v. Colgate')
'U.S. Steel v. Colgate'
>>> harmonize('papusa')
'papusa'
>>> harmonize('CUSANO')
'CUSANO'
>>> harmonize('US Steel v.  US')
'US Steel v. United States'
>>> harmonize('US v. V.Vivack')
'United States v. V.Vivack'
>>> harmonize('US vs. Lissner')
'United States v. Lissner'
>>> harmonize('vs.boxer@gmail.com vs. USA')
'vs.boxer@gmail.com v. United States'
>>> harmonize('US v. US')
'United States v. United States'
>>> harmonize('US  Steel v.  US')
'US  Steel v. United States'
>>> harmonize('Lissner, et. al.')
'Lissner'
>>> harmonize('Lissner, et. al')
'Lissner'
>>> harmonize('Lissner, et al.')
'Lissner'
>>> harmonize('Lissner, et al')
'Lissner'
>>> harmonize('Lissner et. al.')
'Lissner'
>>> harmonize('Lissner et. al')
'Lissner'
>>> harmonize('Lissner et al.')
'Lissner'
>>> harmonize('Lissner et al')
'Lissner'
>>> harmonize('clarinet alibi')
'clarinet alibi'
"""}

