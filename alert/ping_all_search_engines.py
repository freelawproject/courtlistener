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

import settings
from django.core.management import setup_environ
setup_environ(settings)

from django.contrib.sitemaps import ping_google


def main():
    pinged = []
    sitemap_url = '/sitemap.xml'
    for ping_url in settings.SITEMAP_PING_URLS :
        ping_google(sitemap_url, ping_url)
        pinged.append(ping_url + " has been pinged")
    for foo in pinged:
        print foo
    return 0

if __name__ == '__main__':
    main()
