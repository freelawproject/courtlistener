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

import os

from alert.settings import DUMP_DIR
from datetime import datetime
from django.shortcuts import render_to_response
from django.template import RequestContext

def display_dump_page(request):
    '''
    Builds a table of the data dumps, and then displays the page to the user.
    '''
    os.chdir(DUMP_DIR)

    dump_files = os.listdir('.')
    dump_files.sort()
    dumps_info = []
    latest_dumps_info = []
    for dump_file in dump_files:
        # For each file, gather up the information about it
        dump = []
        # Creation date
        dump.append(datetime.fromtimestamp(os.path.getctime(dump_file)))
        # Filename
        dump.append(dump_file)
        # Filesize
        dump.append(os.stat(dump_file)[6])

        if 'latest' in dump_file:
            latest_dumps_info.append(dump)
        else:
            dumps_info.append(dump)

    return render_to_response('dumps/dumps.html', {'dumps_info': dumps_info,
        'latest_dumps_info': latest_dumps_info}, RequestContext(request))
