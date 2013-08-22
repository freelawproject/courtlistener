import os
import sys
sys.path.append(os.getenv('CL_INSTALL_ROOT', '/var/www/courtlistener'))

import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.alerts.models import Alert
from optparse import OptionParser


def fixer(simulate=False, verbose=False):
    '''If an alert is set up to query ALL courts with them individually listed,
    simply strip out all the court values.'''
    alerts = Alert.objects.filter(alertText__contains='court_all')

    for alert in alerts:
        if verbose:
            print "Fixing alert %s" % (alert)
            print "  Old query: %s" % alert.alertText
        q = alert.alertText
        q_parts = q.split('&')
        q_parts = [q for q in q_parts if not q.startswith('court_')]
        alert.alertText = '&'.join(q_parts)
        if verbose:
            print "  New query: %s" % alert.alertText
        if not simulate:
            alert.save()


def main():
    usage = "usage: %prog [--verbose] [---simulate]"
    parser = OptionParser(usage)
    parser.add_option('-v', '--verbose', action="store_true", dest='verbose',
        default=False, help="Display log during execution")
    parser.add_option('-s', '--simulate', action="store_true",
        dest='simulate', default=False, help=("Simulate the corrections "
                                              "without actually making them."))
    (options, args) = parser.parse_args()

    verbose = options.verbose
    simulate = options.simulate

    if simulate:
        print "*******************************************"
        print "* SIMULATE MODE - NO CHANGES WILL BE MADE *"
        print "*******************************************"

    return fixer(simulate, verbose)
    exit(0)

if __name__ == '__main__':
    main()
