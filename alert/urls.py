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

# imports of local settings and views
from alert import settings
from alert.alertSystem.views import *
from alert.alertSystem.sitemap import DocumentSitemap
from alert.contact.views import *
from alert.emailer.views import *
from alert.search.views import *
from alert.userHandling.views import *

# needed to make urls work
from django.conf.urls.defaults import *

# for the flatfiles in the sitemap
from django.contrib.sitemaps import FlatPageSitemap
from django.contrib.auth.views import login as signIn, logout as signOut,\
    password_reset, password_reset_done, password_reset_confirm,\
    password_reset_complete

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

sitemaps = {
    "Opinion": DocumentSitemap,
    "Flatfiles": FlatPageSitemap,
}

urlpatterns = patterns('',
    # Admin docs and site
    (r'^admin/doc/', include('django.contrib.admindocs.urls')),
    (r'^admin/', include(admin.site.urls)),

    # The scraper, parser and emailer URLs
    (r'^scrape/(\d{1,2})/$', scrape),
    (r'^parse/(\d{1,2})/$', parse),
    (r'^email/(daily|weekly|monthly)/$', emailer),

    # Sitemap generator
    (r'^sitemap\.xml$', 'django.contrib.sitemaps.views.sitemap',
        {'sitemaps': sitemaps}),

    # Court listing pages
    (r'^opinions/(ca1|ca2|ca3|ca4|ca5|ca6|ca7|ca8|ca9|ca10|ca11|cadc|cafc|all)/$',
        viewDocumentListByCourt),

    # Display a case
    url(r'^(ca1|ca2|ca3|ca4|ca5|ca6|ca7|ca8|ca9|ca10|ca11|cadc|cafc)/(.*)/$',
        viewCases, name="viewCases"),

    # Contact us pages
    (r'^contact/$', contact),
    (r'^contact/thanks/$', thanks),
    
    # Various sign in/out etc. functions as provided by django
    (r'^sign-out/$', signOut),
    (r'^sign-in/$', signIn),
    
    # Homepage!
    (r'^$', home),
    
    # Settings pages
    (r'^profile/settings/$', viewSettings),
    (r'^profile/alerts/$', viewAlerts),
    (r'^profile/password/change/$', password_change),
    (r'^profile/delete/$', deleteProfile),
    (r'^profile/delete/done/$', deleteProfileDone),
    (r'^register/$', register),
    (r'^register/success/$', registerSuccess),
    
    #Reset password pages
    (r'^reset-password/$', password_reset),
    (r'^reset-password/instructions-sent/$', password_reset_done),
    (r'^confirm-password/(?P<uidb36>.*)/(?P<token>.*)/$', password_reset_confirm),
    (r'^reset-password/complete/$', password_reset_complete),

    # Alert/search pages
    (r'^(alert/preview)/$', showResults),
    (r'^(search/results)/$', showResults),
    (r'^alert/edit/(\d{1,6})/$', editAlert),
    (r'^alert/delete/(\d{1,6})/$', deleteAlert),    
)

# if it's not the production site, serve the static files this way.
if settings.DEVELOPMENT:
    urlpatterns += patterns('',
    (r'^media/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': '/home/mlissner/Documents/Cal/Final Project/alert/assets/media',
        'show_indexes': True}),
    (r'^500/$', 'django.views.generic.simple.direct_to_template',
        {'template': '500.html'}),
    (r'^404/$', 'django.views.generic.simple.direct_to_template',
        {'template': '404.html'}),
)
