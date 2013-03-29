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

import settings
from django.core.management import setup_environ
setup_environ(settings)

from datetime import date

from alert.search.models import Document
from alert.lib.dump_lib import make_dump_file
from alert.lib.db_tools import queryset_generator_by_date
from alert.settings import DUMP_DIR


def dump_all_cases():
    '''
    A simple function that dumps all cases to a single dump file. Rotates out
    the old file before deleting it.
    '''
    today = date.today()
    start_date = date(1754, 9, 1)  # First American case
    end_date = date(today.year, today.month, today.day)
    # Get the documents from the database.
    qs = Document.objects.all()
    docs_to_dump = queryset_generator_by_date(qs,
                                              'dateFiled',
                                              start_date,
                                              end_date)

    path_from_root = DUMP_DIR
    filename = 'all.xml'
    make_dump_file(docs_to_dump, path_from_root, filename)

    return 0


def main():
    '''Runs the script.

    Returns 0 if successful, else returns 1.
    '''
    return dump_all_cases()

if __name__ == '__main__':
    main()
