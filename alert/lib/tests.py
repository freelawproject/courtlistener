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
unittest). These will both pass when you run "manage.py test alerts".

Replace these with more appropriate tests for your application.
"""

from django.test import TestCase
from lib.string_utils import clean_string
from lib.string_utils import harmonize

class SimpleTest(TestCase):
    def test_basic_addition(self):
        """
        Tests that 1 + 1 always equals 2.
        """
        self.failUnlessEqual(1 + 1, 2)

__test__ = {"doctest": """
>>> harmonize(clean_string('U.S.A. v. Lissner'))
'United States v. Lissner'
>>> harmonize(clean_string('U.S. v. Lissner'))
'United States v. Lissner'
>>> harmonize(clean_string('U. S. v. Lissner'))
'United States v. Lissner'
>>> harmonize(clean_string('United States v. Lissner'))
'United States v. Lissner'
>>> harmonize(clean_string('Usa v. Lissner'))
'United States v. Lissner'
>>> harmonize(clean_string('USA v. Lissner'))
'United States v. Lissner'
>>> harmonize(clean_string('United States of America v. Lissner'))
'United States v. Lissner'
>>> harmonize(clean_string('Lissner v. United States of America'))
'Lissner v. United States'
>>> harmonize(clean_string('V.Vivack and Associates v. US'))
'V.Vivack and Associates v. United States'
>>> harmonize(clean_string('v.v. Hendricks & Sons v. James v. Smith'))
'v.v. Hendricks & Sons v. James v. Smith'
>>> harmonize(clean_string('U.S.A. v. Mr. v.'))
'United States v. Mr. v.'
>>> harmonize(clean_string('U.S.S. v. Lissner'))
'U.S.S. v. Lissner'
>>> harmonize(clean_string('USC v. Lissner'))
'USC v. Lissner'
>>> harmonize(clean_string('U.S.C. v. Lissner'))
'U.S.C. v. Lissner'
>>> harmonize(clean_string('U.S. Steel v. Colgate'))
'U.S. Steel v. Colgate'
>>> harmonize(clean_string('papusa'))
'papusa'
>>> harmonize(clean_string('CUSANO'))
'CUSANO'
>>> harmonize(clean_string('US Steel v.  US'))
'US Steel v. United States'
>>> harmonize(clean_string('US v. V.Vivack'))
'United States v. V.Vivack'
>>> harmonize(clean_string('US vs. Lissner'))
'United States v. Lissner'
>>> harmonize(clean_string('vs.boxer@gmail.com vs. USA'))
'vs.boxer@gmail.com v. United States'
>>> harmonize(clean_string('US v. US'))
'United States v. United States'
>>> harmonize(clean_string('US  Steel v.  US'))
'US  Steel v. United States'
>>> harmonize(clean_string('Lissner, et. al.'))
'Lissner'
>>> harmonize(clean_string('Lissner, et. al'))
'Lissner'
>>> harmonize(clean_string('Lissner, et al.'))
'Lissner'
>>> harmonize(clean_string('Lissner, et al'))
'Lissner'
>>> harmonize(clean_string('Lissner et. al.'))
'Lissner'
>>> harmonize(clean_string('Lissner et. al'))
'Lissner'
>>> harmonize(clean_string('Lissner et al.'))
'Lissner'
>>> harmonize(clean_string('Lissner et al'))
'Lissner'
>>> harmonize(clean_string('clarinet alibi'))
'clarinet alibi'
>>> harmonize(clean_string('US v. Lissner, Plaintiff'))
'United States v. Lissner'
>>> harmonize(clean_string('US v. Lissner, Petitioner-appellant'))
'United States v. Lissner'
>>> harmonize(clean_string('United States, Petitioner, v. Lissner'))
'United States v. Lissner'
>>> harmonize(clean_string('United States of America, Plaintiff-Appellee, v. Orlando B. Pino, Defendant-Appellant, Joseph'))
'United States v. Orlando B. Pino, Joseph'
>>> harmonize(clean_string('Herring v. U.S. **'))
'Herring v. United States'
>>> harmonize(clean_string('Test v. U.S'))
'Test v. United States'
>>> harmonize(clean_string('The United States v. Lissner'))
'United States v. Lissner'
"""}
