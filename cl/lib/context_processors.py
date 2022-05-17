import random
from datetime import datetime

from django.conf import settings
from django.http import HttpRequest
from django.urls import reverse

from cl.search.models import SEARCH_TYPES
from cl.users.models import (
    EMAIL_NOTIFICATIONS,
    OBJECT_TYPES,
    BackoffEvent,
    EmailFlag,
)


def inject_settings(request):
    """Use this function to inject specific settings into every page."""
    return {
        "DEBUG": settings.DEBUG,
        "EIN_SECRET": settings.EIN_SECRET,
        "MIN_DONATION": settings.MIN_DONATION,
        "MAX_ALERT_RESULTS_PER_DAY": settings.MAX_ALERT_RESULTS_PER_DAY,
        "FUNDRAISING_MODE": settings.FUNDRAISING_MODE,
        "MAX_FREE_DOCKET_ALERTS": settings.MAX_FREE_DOCKET_ALERTS,
        "DOCKET_ALERT_RECAP_BONUS": settings.DOCKET_ALERT_RECAP_BONUS,
        "SEARCH_TYPES": SEARCH_TYPES,
    }


info_tips = (
    # Other Projects
    'CourtListener is powered by <a href="https://github.com/freelawproject/juriscraper">more than 200 screen scrapers</a> that run every hour of every day.',
    'We are collecting <a href="https://github.com/freelawproject/seal-rookery">all of the court seals in the U.S.</a> You can help contribute seals.',
    'We <a href="https://github.com/freelawproject/judge-pics">have a collection of more than 1,200 judicial portraits</a> and we need volunteers to help collect them all.',
    # History
    'CourtListener was started in 2009 to create alerts for the federal appeals courts. It has since grown into the <a href="%s?referrer=tip">user-supported</a> non-profit Free Law Project.'
    % reverse("donate"),
    'We host and maintain <a href="https://free.law/2020/03/10/courts-db-a-new-open-database/">a massive database of court identifiers and information</a> we call the Court-DB',
    # Non-profit and fundraising
    'Free Law Project is a 501(c)(3) non-profit that relies on your support to operate. Please <a href="%s?referrer=tip">donate</a> to support this site</a>. <i class="fa fa-heart red"></i>'
    % reverse("donate"),
    'CourtListener gets more than two million visits per year, but has a lean staff of only a few developers. Please <a href="%s?referrer=tip">donate</a> to support this site. <i class="fa fa-heart red"></i>'
    % reverse("donate"),
    'CourtListener is supported by <a href="%s?referrer=tip">user donations</a> and small grants. More donations result in less time spent seeking grants and more time adding features. <i class="fa fa-heart red"></i>'
    % reverse("donate"),
    'Free Law Project is a member of the <a href="http://www.falm.info/">Free Access to Law Movement</a> and relies heavily on <a href="%s?referrer=tip">your donations</a>. <i class="fa fa-heart red"></i>'
    % reverse("donate"),
    'Using <a href="https://smile.amazon.com/ch/46-3342480">smile.amazon.com</a>, you can donate 0.5% of every purchase you make on Amazon to Free Law Project, the non-profit that sponsors CourtListener. <i class="fa fa-heart red"></i>',
    'Free Law Project, the non-profit behind CourtListener, provides <a href="https://free.law/data-consulting/">data consulting and client services</a> for those that need help with our data.',
    'If you have a Github account, you <a href="https://github.com/sponsors/freelawproject/">can sponsor our work</a> so we can do more of it. <i class="fa fa-heart red"></i>',
    # Recognition
    'Free Law Project\'s founders were <a href="https://free.law/2014/07/14/free-law-project-co-founders-named-to-fastcase-50-for-2014/">selected as FastCase 50 winners in 2014</a>.',
    'Oral Arguments were <a href="https://free.law/2014/12/04/free-law-project-recognized-in-two-of-top-ten-legal-hacks-of-2014-by-dc-legal-hackers/">selected as a Top Ten Legal Hack of 2014</a>.',
    'In 2017, Free Law Project <a href="https://free.law/2017/01/10/le-hackie-2016/">was awarded a Le Hackie from D.C. Legal Hackers</a> for our research and blogging about PACER.'
    # Open source
    'All of the code powering CourtListener is <a href="https://github.com/freelawproject/courtlistener">open source</a> and can be copied, shared, and contributed to.',
    'We need volunteers to help us with coding, design, and legal research. <a href="%s">Contact us for more info</a>.'
    % reverse("contact"),
    'The current design of CourtListener was <a href="https://free.law/2014/11/13/check-out-courtlisteners-new-paint-and-features/">created by a volunteer</a>.',
    # Neutral Citations
    'WestLaw currently has a monopoly on citations. This hinders legal innovation but few courts have adopted <a href="%s#explain-neutral-citations">neutral citations</a>.'
    % reverse("faq"),
    # Features
    'You can <a href="%s">create an alert</a> for any query to receive an email if the query has new results.'
    % reverse("alert_help"),
    'There is an <a href="%s">RSS feed</a> for every query so you can easily stay up to date.'
    % reverse("feeds_info"),
    'Search relevancy on CourtListener is <a href="https://free.law/2013/11/12/citegeist/">highly tuned and is powered by the citation network between cases</a>.',
    'You can make sophisticated queries using a number of <a href="%s">advanced search features</a>.'
    % reverse("advanced_search"),
    'You can get an alert whenever an opinion is cited by <a href="https://free.law/2020/02/20/citation-alerts/">using a Citation Search</a>.',
    'We <a href="https://free.law/2016/02/22/viz/">partnered with University of Baltimore</a> to make a system of visualizing Supreme Court Cases.',
    'Information from the Supreme Court Database <a href="https://free.law/2016/09/06/legacy-scdb/">is available for nearly every SCOTUS case</a>, making it easy to get in-depth analysis.',
    # Oral Arguments
    'A podcast is created for every oral argument query that you make using <a href="%s">the oral Argument search engine</a>.'
    % reverse("advanced_oa"),
    'CourtListener has an <a href="%s">API</a> so anybody can easily use our data.'
    % reverse("api_index"),
    'Oral argument podcasts <a href="%s">are available in variety of apps</a> like iTunes, Stitcher Radio, and Google Music.'
    % reverse("podcasts"),
    "We have more than a million minutes of oral argument audio. More than anywhere else on the Internet.",
    # RECAP & PACER
    '<a href="https://free.law/recap/">RECAP</a> is our browser extension that saves you money whenever you use PACER.',
    'Using the <a href="https://free.law/recap/">RECAP project</a> means never paying for the same PACER document twice.',
    'RECAP was originally created at <a href="https://citp.princeton.edu">The Center for Information Technology Policy at Princeton University</a>.',
    "PACER was created by Congress and makes around $140,000,000/year selling public domain legal documents.",
    "With an estimated 1 billion documents, PACER is the largest paywall in the world.",
    'The average PACER document is <a href="https://twitter.com/RECAPtheLaw/status/771585725875691520">9.1 pages long</a>. The longest we\'ve seen so far is over 4,000 pages.',
    'Downloading everything in PACER <a href="https://free.law/2016/10/10/pacer-costs-a-billion-dollars/">would cost around $1,000,000,000</a>.',
    'We extract text from every PACER document so that it is searchable. <a href="https://free.law/2016/09/26/extracting-text-millions-of-pacer-documents/">This takes months</a>!',
    'CourtListener has <a href="https://free.law/2017/08/15/we-have-all-free-pacer/">every free opinion and order available in PACER</a> and gets the latest ones every night.',
    'Want to learn more about PACER? <a href="https://free.law/pacer-facts/">We have an extensive fact sheet</a>.',
    'You can <a href="https://free.law/recap/hacking-recap-links/">use the link to any RECAP PDF to pull up the docket</a>.',
    "We have more than 80 million pages of PACER documents searchable in the RECAP Archive.",
    'You can <a href="%s">create an alert for any docket in the RECAP Archive</a>. Just press the "Get Alerts" button.'
    % reverse("alert_help"),
)


def inject_random_tip(request):
    return {"TIP": random.choice(info_tips)}


PERMANENT = {
    EMAIL_NOTIFICATIONS.GENERAL: "Your email provider sent a hard "
    "bounce message indicating we can't continue sending messages to your "
    "current email address. "
    "Please consider changing your email address.",
    EMAIL_NOTIFICATIONS.NO_EMAIL: "Your email provider sent a bounce "
    "message indicating that your email address doesn't exist. Please "
    "consider changing your email address.",
    EMAIL_NOTIFICATIONS.COMPLAINT: "We've received a complaint from "
    "your email provider indicating that you don't want to receive emails "
    "from us. Please consider changing your email address.",
}

TRANSIENT = {
    EMAIL_NOTIFICATIONS.GENERAL: "The last messages we sent to your email "
    "address have bounced back. We are still attempting to fix this problem "
    "by resending messages.",
    EMAIL_NOTIFICATIONS.MAILBOX_FULL: "Your email provider sent a "
    "bounce message because your inbox was full. Please consider clearing out "
    "your email inbox.",
}


def validate_email_address(
    request: HttpRequest,
) -> dict[str, datetime | str] | dict:
    """This function injects the status of the user's email address.

    :param request: Contains the user for checking if their email is valid.
    return dict: The message and date for the user's email status.
    """
    if request.user.is_authenticated:
        email = request.user.email
        email_banned = EmailFlag.objects.filter(
            email_address=email, object_type=OBJECT_TYPES.BAN
        )
        if email_banned.exists():
            msg = PERMANENT.get(
                email_banned[0].event_sub_type,
                PERMANENT[EMAIL_NOTIFICATIONS.GENERAL],
            )
            return {
                "email_banned_date": email_banned[0].date_created,
                "email_msg": msg,
            }
        backoff_event = BackoffEvent.objects.filter(email_address=email)
        if backoff_event.exists():
            msg = TRANSIENT.get(
                backoff_event[0].notification_subtype,
                TRANSIENT[EMAIL_NOTIFICATIONS.GENERAL],
            )
            return {"email_msg": msg}
    return {}
