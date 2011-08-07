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
unittest). These will both pass when you run "manage.py test alertSystem".

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
>>> clean_string(harmonize('U.S.A. v. Lissner'))
'United States v. Lissner'
>>> clean_string(harmonize('U.S. v. Lissner'))
'United States v. Lissner'
>>> clean_string(harmonize('U. S. v. Lissner'))
'United States v. Lissner'
>>> clean_string(harmonize('United States v. Lissner'))
'United States v. Lissner'
>>> clean_string(harmonize('Usa v. Lissner'))
'United States v. Lissner'
>>> clean_string(harmonize('USA v. Lissner'))
'United States v. Lissner'
>>> clean_string(harmonize('United States of America v. Lissner'))
'United States v. Lissner'
>>> clean_string(harmonize('Lissner v. United States of America'))
'Lissner v. United States'
>>> clean_string(harmonize('V.Vivack and Associates v. US'))
'V.Vivack and Associates v. United States'
>>> clean_string(harmonize('v.v. Hendricks & Sons v. James v. Smith'))
'v.v. Hendricks & Sons v. James v. Smith'
>>> clean_string(harmonize('U.S.A. v. Mr. v.'))
'United States v. Mr. v.'
>>> clean_string(harmonize('U.S.S. v. Lissner'))
'U.S.S. v. Lissner'
>>> clean_string(harmonize('USC v. Lissner'))
'USC v. Lissner'
>>> clean_string(harmonize('U.S.C. v. Lissner'))
'U.S.C. v. Lissner'
>>> clean_string(harmonize('U.S. Steel v. Colgate'))
'U.S. Steel v. Colgate'
>>> clean_string(harmonize('papusa'))
'papusa'
>>> clean_string(harmonize('CUSANO'))
'CUSANO'
>>> clean_string(harmonize('US Steel v.  US'))
'US Steel v. United States'
>>> clean_string(harmonize('US v. V.Vivack'))
'United States v. V.Vivack'
>>> clean_string(harmonize('US vs. Lissner'))
'United States v. Lissner'
>>> clean_string(harmonize('vs.boxer@gmail.com vs. USA'))
'vs.boxer@gmail.com v. United States'
>>> clean_string(harmonize('US v. US'))
'United States v. United States'
>>> clean_string(harmonize('US  Steel v.  US'))
'US  Steel v. United States'
>>> clean_string(harmonize('Lissner, et. al.'))
'Lissner'
>>> clean_string(harmonize('Lissner, et. al'))
'Lissner'
>>> clean_string(harmonize('Lissner, et al.'))
'Lissner'
>>> clean_string(harmonize('Lissner, et al'))
'Lissner'
>>> clean_string(harmonize('Lissner et. al.'))
'Lissner'
>>> clean_string(harmonize('Lissner et. al'))
'Lissner'
>>> clean_string(harmonize('Lissner et al.'))
'Lissner'
>>> clean_string(harmonize('Lissner et al'))
'Lissner'
>>> clean_string(harmonize('clarinet alibi'))
'clarinet alibi'
>>> clean_string(harmonize('US v. Lissner, Plaintiff'))
'United States v. Lissner'
>>> clean_string(harmonize('US v. Lissner, Petitioner-appellant'))
'United States v. Lissner'
"""}
