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


from alert.alertSystem.models import Document
from django.http import HttpResponse
from django.template import loader, Context
from django.views.decorators.cache import cache_page


@cache_page(60 * 60)
def robots(request):
    '''Generate the robots.txt file'''
    response = HttpResponse(mimetype = 'text/plain')

    docs = Document.objects.filter(blocked = True).order_by('date_blocked')

    # make them into pretty HTML
    t = loader.get_template('robots/robots.txt')
    c = Context({'docs': docs})
    text = t.render(c)
    response.write(text)
    return response

