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
from alert.alertSystem.models import PACER_CODES
from alert.alertSystem.views import *
from alert.contact.views import *
from alert.feeds.views import *
from alert.pinger.views import *
from alert.search.views import *
from alert.userHandling.views import *
# this imports a variable that can be handed to the sitemap index generator function.
from alert.alertSystem.sitemap import all_sitemaps as sitemaps
from alert.alertSystem.sitemap import sitemap
from django.conf.urls.defaults import *

# for the flatfiles in the sitemap
from django.contrib.auth.views import login as signIn, logout as signOut,\
    password_reset, password_reset_done, password_reset_confirm,\
    password_reset_complete

# enables the admin:
from django.contrib import admin
admin.autodiscover()

# creates a list of the first element of the choices variable for the courts field
pacer_codes = []
for code in PACER_CODES:
    pacer_codes.append(code[0])

urlpatterns = patterns('',
    # Admin docs and site
    (r'^admin/doc/', include('django.contrib.admindocs.urls')),
    (r'^admin/', include(admin.site.urls)),

    # Court listing pages
    (r'^opinions/(' + "|".join(pacer_codes) + '|all)/$', viewDocumentListByCourt),

    # Display a case, a named URL because the get_absolute_url uses it.
    url(r'^(' + "|".join(pacer_codes) + ')/(.*)/$', viewCases, name="viewCases"),

    # Contact us pages
    (r'^contact/$', contact),
    (r'^contact/thanks/$', thanks),
    
    # Various sign in/out etc. functions as provided by django
    url(r'^sign-in-register/$', combined_signin_register, name="sign-in-register"),
    url(r'^sign-in/$', signIn, name="sign-in"),
    (r'^sign-out/$', signOut),

    # Homepage and favicon
    (r'^$', home),
    (r'^favicon\.ico$', 'django.views.generic.simple.redirect_to', {'url': '/media/images/ico/favicon.ico'}),

    # Settings pages
    (r'^profile/settings/$', viewSettings),
    (r'^profile/alerts/$', viewAlerts),
    (r'^profile/password/change/$', password_change),
    (r'^profile/delete/$', deleteProfile),
    (r'^profile/delete/done/$', deleteProfileDone),
    url(r'^register/$', register, name="register"),

    #Reset password pages
    (r'^reset-password/$', password_reset),
    (r'^reset-password/instructions-sent/$', password_reset_done),
    (r'^confirm-password/(?P<uidb36>.*)/(?P<token>.*)/$', password_reset_confirm, {'post_reset_redirect': '/reset-password/complete/'}),
    (r'^reset-password/complete/$', signIn, {'template_name': 'registration/password_reset_complete.html'}),

    # Alert/search pages
    # These URLs support either GET requests or things like /alert/preview/searchterm.
    #url(r'^(alert/preview)/$', showResults, name="alertResults"),
    url(r'^search/results/$', showResults, name="searchResults"),
    (r'^search/$', showResults), #for the URL hackers in the crowd
    (r'^alert/edit/(\d{1,6})/$', editAlert),
    (r'^alert/delete/(\d{1,6})/$', deleteAlert),
    (r'^alert/delete/confirm/(\d{1,6})/$', deleteAlertConfirm),
    (r'^tools/$', toolsPage),

    # Feeds
    (r'^feed/(search)/$', searchFeed()), #lacks URL capturing b/c it will use GET queries.
    (r'^feed/court/all/$', allCourtsFeed()),
    (r'^feed/court/(?P<court>' + '|'.join(pacer_codes) + ')/$', courtFeed()),

    # SEO-related stuff
    (r'^y_key_6de7ece99e1672f2.html$', validateForYahoo),
    (r'^LiveSearchSiteAuth.xml$', validateForBing),
    (r'^googleef3d845637ccb353.html$', validateForGoogle),
    # Sitemap index generator
    (r'^sitemap\.xml$', 'django.contrib.sitemaps.views.index',
        {'sitemaps': sitemaps}),
    # this uses a custom sitemap generator that has a file-based cache.    
    (r'^sitemap-(?P<section>.+)\.xml$', 'django.contrib.sitemaps.views.sitemap', {'sitemaps': sitemaps}),
    #(r'^robots.txt$', robots), # removed for lack of need.
)

# redirects
urlpatterns += patterns('django.views.generic.simple',
    ('^privacy/$', 'redirect_to', {'url': '/terms/#privacy'}),
    ('^removal/$', 'redirect_to', {'url': '/terms/#removal'}),
    ('^opinions/$', 'redirect_to', {'url': '/opinions/all/'}),
    ('^report/$', 'redirect_to', {'url': 'http://www.ischool.berkeley.edu/files/student_projects/Final_Report_Michael_Lissner_2010-05-07_2.pdf'}),
)


# if it's not the production site, serve the static files this way.
if settings.DEVELOPMENT:
    urlpatterns += patterns('',
    (r'^media/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': settings.INSTALL_ROOT + 'alert/assets/media',
        'show_indexes': True}),
    (r'^500/$', 'django.views.generic.simple.direct_to_template',
        {'template': '500.html'}),
    (r'^404/$', 'django.views.generic.simple.direct_to_template',
        {'template': '404.html'}),
)
