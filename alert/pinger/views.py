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
from django.shortcuts import render_to_response
from django.template import RequestContext

from django.conf import settings
from django.core.urlresolvers import reverse

def validateForYahoo(request):
    return HttpResponse('36e23db9b9505bbb')

def validateForBing(request):
    return HttpResponse('<?xml version="1.0"?><users><user>3251009A11EF3EB9D6A7B40EAD9264AD</user></users>')

def validateForGoogle(request):
    return HttpResponse('google-site-verification: googleef3d845637ccb353.html')

def robots(request):
    robots = "User-agent: *\
Disallow: "
    return HttpResponse(robots)
