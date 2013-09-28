import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from django.contrib.sitemaps import ping_google
from django.conf import settings


def main():
    pinged = []
    sitemap_url = '/sitemap.xml'
    for ping_url in settings.SITEMAP_PING_URLS:
        try:
            ping_google(sitemap_url, ping_url)
            pinged.append("%s has been pinged." % ping_url)
        except IOError:
            pinged.append("****%s FAILED with an IOError.****" % ping_url)
            print >> sys.stderr, "****%s FAILED with an IOError.****" % ping_url
    for foo in pinged:
        print foo
    return 0

if __name__ == '__main__':
    main()
