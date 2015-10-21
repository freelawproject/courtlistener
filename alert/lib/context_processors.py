import random
from django.conf import settings


def inject_settings(request):
    return {
        'DEBUG': settings.DEBUG,
        'MIN_DONATION': settings.MIN_DONATION
    }


info_tips = (
    # RECAP
    '<a href="http://www.recapthelaw.org" target="_blank">RECAP</a> is our browser extension that saves you money whenever you use PACER.',
    'Using the <a href="http://www.recapthelaw.org">RECAP project</a> means never paying for the same PACER document twice.',

    # Juriscraper
    'CourtListener is powered by <a href="https://github.com/freelawproject/juriscraper" target="_blank">more than 200 screen scrapers</a>.',

    # Seal Rookery
    'We are collecting <a href="https://github.com/freelawproject/seal-rookery" target="_blank">all of the court seals in the U.S.</a> You can help contribute seals.',

    # History
    'CourtListener was started in 2009 to create alerts for the Federal Appeals Courts. It has since grown into the <a href="/donate/?referrer=tip">user-supported</a> non-profit Free Law Project.',

    # Non-profit
    'Free Law Project is a 501(c)(3) non-profit that relies on your support to operate. Please <a href="/donate/?referrer=tip" target="_blank">donate</a> to support this site.',
    'CourtListener gets more than two million visits per year, but has a lean staff of only a few developers. Please <a href="/donate/?referrer=tip" target="_blank">donate</a> to support this site.',
    'CourtListener is supported by <a href="/donate/?referrer=tip">user donations</a> and small grants. More donations result in less time spent seeking grants and more time adding features.',
    'Free Law Project is a member of the <a href="http://www.falm.info/" target="_blank">Free Access to Law Movement</a> and relies heavily on <a href="/donate/?referrer=tip">your donations</a>.',

    # Recognition
    'Free Law Project\'s founders were <a href="http://freelawproject.org/2014/07/14/free-law-project-co-founders-named-to-fastcase-50-for-2014/" target="_blank">selected as FastCase 50 winners in 2014</a>.',
    'Oral Arguments were <a href="http://freelawproject.org/2014/12/04/free-law-project-recognized-in-two-of-top-ten-legal-hacks-of-2014-by-dc-legal-hackers/" target="_blank">selected as a Top Ten Legal Hack of 2014</a>.',

    # Open source
    'All of code powering CourtListener is <a href="https://github.com/freelawproject/courtlistener" target="_blank">open source</a> and can be copied, shared, and contributed to.',
    'We need volunteers to help us with coding, design and legal research. <a href="/contact/" target="_blank">Contact us for more info</a> or check out our <a href="https://trello.com/b/l0qS4yhd/assistance-needed" target="_blank">help wanted board</a> to get started.',
    'The current design of CourtListener was <a href="http://freelawproject.org/2014/11/13/check-out-courtlisteners-new-paint-and-features/" target="_blank">created by a volunteer</a>.',

    # Neutral Citations
    'WestLaw currently has a monopoly on citations. This hinders legal innovation but few courts have adopted <a href="/faq/#explain-neutral-citations">neutral citations</a>.',

    # Alerts, RSS & Podcasts, API, Search
    'Create alerts for any query to receive an email if the query has new results.',
    'There is an <a href="/feeds/">RSS feed</a> for every query so you can easily stay up to date.',
    'A podcast is created for every oral argument query that you make.',
    'CourtListener has an <a href="/api/">API</a> so anybody can easily use our data.',
    'Oral Arguments are available in <a href="http://freelawproject.org/2014/11/09/more-oral-argument-news/">Stitcher Radio</a>.',
    'Search Relevancy on CourtListener is <a href="http://freelawproject.org/2013/11/12/courtlistener-improves-search-results-thanks-to-volunteer-contributor/" target="_blank">powered by the citation network between cases.</a>',
    'You can make sophisticated queries using a number of <a href="/search/advanced-techniques/">advanced search features</a>.',
)
def inject_random_tip(request):
    return {'TIP': random.choice(info_tips)}
