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


from django.template import Library
from django.template.defaultfilters import stringfilter
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

import re

register = Library()

@register.filter
@stringfilter
def nbsp(text, autoescape=None):
    '''Converts white space to non-breaking spaces

    This creates a template filter that converts white space to html non-breaking
    spaces. It uses conditional_escape to escape any strings that are incoming
    and are not already marked as safe.
    '''
    if autoescape:
        esc = conditional_escape
    else:
        # This is an anonymous python identity function. Simply returns the value
        # of x when x is given.
        esc = lambda x: x
    return mark_safe(re.sub('\s','&nbsp;',esc(text.strip())))
nbsp.needs_autoescape = True


@register.filter
@stringfilter
def v_wrapper(text, autoescape=None):
    '''Wraps every v. in a string with a class of alt'''
    if autoescape:
        esc = conditional_escape
    else:
        esc = lambda x: x
    return mark_safe(re.sub('v\.', '<span class="alt bold">v.</span>', esc(text)))
v_wrapper.needs_autoescape = True
