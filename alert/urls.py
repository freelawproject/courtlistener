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
from alert.casepage.sitemap import sitemap_maker, flat_sitemap_maker
from alert.casepage.views import view_case, view_case_citations, \
                                 serve_static_file
from alert.contact.views import contact, thanks
from alert.data_dumper.views import dump_index, serve_or_gen_dump
from alert.favorites.views import delete_favorite, edit_favorite, \
                                  save_or_update_favorite
from alert.feeds.views import all_courts_feed, cited_by_feed, court_feed, \
                              search_feed
from alert.maintenance_warning.views import show_maintenance_warning
from alert.pinger.views import validate_for_bing, validate_for_bing2, \
                               validate_for_google, validate_for_google2, \
                               validate_for_google3
from alert.robots.views import robots
from alert.alerts.views import delete_alert, delete_alert_confirm, edit_alert
from alert.search.models import Court
from alert.search.views import browser_warning, show_results, tools_page
from alert.tinyurl.views import redirect_short_url
from alert.userHandling.views import confirmEmail, deleteProfile, \
                                     deleteProfileDone, emailConfirmSuccess, \
                                     password_change, redirect_to_settings, \
                                     register, registerSuccess, \
                                     requestEmailConfirmation, view_favorites, \
                                     view_alerts, view_settings

from django.conf.urls.defaults import *

# for the flatfiles in the sitemap
from django.contrib.auth.views import login as signIn, logout as signOut, \
                                      password_reset, password_reset_done, \
                                      password_reset_confirm

# enables the admin:
from django.contrib import admin
admin.autodiscover()

# creates a list of the first element of the choices variable for the courts field
pacer_codes = Court.objects.filter(in_use=True).values_list('courtUUID', flat=True)
mime_types = ('pdf', 'wpd', 'txt', 'doc')

urlpatterns = patterns('',
    # Admin docs and site
    (r'^admin/doc/', include('django.contrib.admindocs.urls')),
    (r'^admin/', include(admin.site.urls)),

    # favicon and apple touch icons
    (r'^favicon\.ico$', 'django.views.generic.simple.redirect_to',
            {'url': '/media/images/ico/favicon.ico'}),
    (r'^apple-touch-icon\.png$', 'django.views.generic.simple.redirect_to',
            {'url': '/media/images/png/apple-touch-icon.png'}),
    (r'^apple-touch-icon-57x57-precomposed\.png$', 'django.views.generic.simple.redirect_to',
            {'url': '/media/images/png/apple-touch-icon-57x57-precomposed.png'}),
    (r'^apple-touch-icon-72x72-precomposed\.png$', 'django.views.generic.simple.redirect_to',
            {'url': '/media/images/png/apple-touch-icon-72x72-precomposed.png'}),
    (r'^apple-touch-icon-114x114-precomposed\.png$', 'django.views.generic.simple.redirect_to',
            {'url': '/media/images/png/apple-touch-icon-114x114-precomposed.png'}),
    (r'^apple-touch-icon-precomposed\.png$', 'django.views.generic.simple.redirect_to',
            {'url': '/media/images/png/apple-touch-icon-precomposed.png'}),
    (r'^bad-browser/$', browser_warning),

    # Maintenance and protest mode!
    #(r'/*', show_maintenance_warning),

    # Display a case's citations page
    url(r'^(?:.*)/(.*)/(.*)/cited-by/$',
        view_case_citations,
        name="view_case_citations"),

    # Display a case; a named URL because the get_absolute_url uses it.
    url(r'^(' + "|".join(pacer_codes) + ')/(.*)/(.*)/$', view_case,
        name="view_case"),

    # Serve a static file
    (r'^(?P<file_path>(?:' + "|".join(mime_types) + ')/.*)$',
        serve_static_file),

    # Redirect users that arrive via crt.li
    (r'^x/(.*)/$', redirect_short_url),

    # Contact us pages
    (r'^contact/$', contact),
    (r'^contact/thanks/$', thanks),

    # Various sign in/out etc. functions as provided by django
    url(r'^sign-in/$', signIn, name="sign-in"),
    (r'^sign-out/$', signOut),

    # Settings pages
    (r'^profile/$', redirect_to_settings),
    url(r'^profile/settings/$', view_settings, name='view_settings'),
    (r'^profile/favorites/$', view_favorites),
    (r'^profile/alerts/$', view_alerts),
    (r'^profile/password/change/$', password_change),
    (r'^profile/delete/$', deleteProfile),
    (r'^profile/delete/done/$', deleteProfileDone),
    url(r'^register/$', register, name="register"),
    (r'^register/success/$', registerSuccess),

    # Favorites pages
    (r'^favorite/create-or-update/$', save_or_update_favorite),
    (r'^favorite/delete/$', delete_favorite),
    (r'^favorite/edit/(\d{1,6})/$', edit_favorite),

    # Registration pages
    (r'^email/confirm/([0-9a-f]{40})/$', confirmEmail),
    (r'^email-confirmation/request/$', requestEmailConfirmation),
    (r'^email-confirmation/success/$', emailConfirmSuccess),

    # Reset password pages
    (r'^reset-password/$', password_reset),
    (r'^reset-password/instructions-sent/$', password_reset_done),
    (r'^confirm-password/(?P<uidb36>.*)/(?P<token>.*)/$',
            password_reset_confirm,
            {'post_reset_redirect': '/reset-password/complete/'}),
    (r'^reset-password/complete/$',
            signIn,
            {'template_name': 'registration/password_reset_complete.html'}),

    # Search pages
    (r'^$', show_results), # the home page

    # Alert pages
    (r'^alert/edit/(\d{1,6})/$', edit_alert),
    (r'^alert/delete/(\d{1,6})/$', delete_alert),
    (r'^alert/delete/confirm/(\d{1,6})/$', delete_alert_confirm),
    (r'^tools/$', tools_page),

    # Dump index and generation pages
    (r'^dump-info/$', dump_index),
    (r'^dump-api/(?P<court>' + "|".join(pacer_codes) + '|all)\.xml.gz$', serve_or_gen_dump),
    (r'^dump-api/(?P<year>\d{4})/(?P<court>' + "|".join(pacer_codes) + '|all)\.xml.gz$', serve_or_gen_dump),
    (r'^dump-api/(?P<year>\d{4})/(?P<month>\d{2})/(?P<court>' + "|".join(pacer_codes) + '|all)\.xml.gz$', serve_or_gen_dump),
    (r'^dump-api/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/(?P<court>' + "|".join(pacer_codes) + '|all)\.xml.gz$', serve_or_gen_dump),

    # Feeds
    (r'^feed/(search)/$', search_feed()), #lacks URL capturing b/c it will use GET queries.
    (r'^feed/court/all/$', all_courts_feed()),
    (r'^feed/court/(?P<court>' + '|'.join(pacer_codes) + ')/$', court_feed()),
    (r'^feed/(?P<doc_id>.*)/cited-by/$', cited_by_feed()),

    # SEO-related stuff
    (r'^LiveSearchSiteAuth.xml$', validate_for_bing),
    (r'^BingSiteAuth.xml$', validate_for_bing2),
    (r'^googleef3d845637ccb353.html$', validate_for_google),
    (r'^google646349975c2495b6.html$', validate_for_google2),
    (r'^google646349975c2495b6.html$', validate_for_google3),

    # Sitemap index generator
    (r'^sitemap\.xml$', sitemap_maker),
    (r'^sitemap-flat\.xml$', flat_sitemap_maker),
    (r'^robots.txt$', robots)
)

# redirects
urlpatterns += patterns('django.views.generic.simple',
    ('^privacy/$', 'redirect_to', {'url': '/terms/#privacy'}),
    ('^removal/$', 'redirect_to', {'url': '/terms/#removal'}),
    ('^browse/$', 'redirect_to', {'url': '/'}),
    ('^opinions/' + "|".join(pacer_codes) + '|all', 'redirect_to', {'url': '/'}), # supports old URLs - added 2011-12-31
    ('^search/results/$', 'redirect_to', {'url': '/', 'query_string': True}), # supports old OpenSearch plugin - added 2012-01-27
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
