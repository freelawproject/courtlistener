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

from django.http import HttpResponse
from django.template import Context, loader
from django.views.decorators.cache import never_cache

class HttpResponseTemporaryUnavailable(HttpResponse):
    status_code = 503

@never_cache
def show_maintenance_warning(request):
    '''Blocks access to a URL, and instead loads a maintenance warning. 
    
    Uses a 503 status code, which preserves SEO. See:
    https://plus.google.com/115984868678744352358/posts/Gas8vjZ5fmB
    '''
    t = loader.get_template('maintenance/maintenance.html')
    return HttpResponseTemporaryUnavailable(t.render(Context({})))
