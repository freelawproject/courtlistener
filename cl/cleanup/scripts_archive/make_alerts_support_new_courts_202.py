import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from alert.alerts.models import Alert
from optparse import OptionParser


def fixer(simulate=False, verbose=False):
    """If an alert is set up to query ALL courts with them individually listed,
    simply strip out all the court values."""
    alerts = Alert.objects.filter(query__contains='court_all')

    for alert in alerts:
        if verbose:
            print "Fixing alert %s" % alert
            print "  Old query: %s" % alert.query
        q = alert.query
        q_parts = q.split('&')
        q_parts = [q for q in q_parts if not q.startswith('court_')]
        alert.query = '&'.join(q_parts)
        if verbose:
            print "  New query: %s" % alert.query
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

if __name__ == '__main__':
    main()
