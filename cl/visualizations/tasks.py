import requests

from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from juriscraper.lib.string_utils import trunc
from lxml import html
from requests.exceptions import HTTPError

from cl.celery import app
from cl.visualizations.models import Referer
from cl.visualizations.utils import emails, new_title_for_viz


def blacklisted_url(url):
    """Check if a URL is blacklisted."""
    blacklist = [
        'content_mobile.php',  # Mobile version of starger's site
        'https://www.courtlistener.com',  # Self-embeds.
        'translate.google',  # Google translate
    ]
    if len([b for b in blacklist if b in url]) > 0:
        return True
    return False


@app.task(bind=True, max_retries=8)
def get_title(self, referer_id):
    """Get the HTML title for a page, trying again if failures occur.

    Idea here is that somebody will create a new page that embeds one of our
    maps. As soon as they do, we'll get an HTTP referer sent to us, which is
    great. Unfortunately, in many cases, the HTTP referer we receive is that of
    an in progress page or similar, NOT the page that's actually live. Thus,
    what we do is try the URL over and over, until we find success.

    If a title is found, the admins are notified.

    If not, the item is deleted (this is OK, however, b/c it'll be recreated if
    it should have existed).
    """
    # Set the exponential back off in case we need it, starting at 15 minutes,
    # then 30, 60, 120...
    countdown = 15 * 60 * (2 ** self.request.retries)
    retried_exceeded = (self.request.retries >= self.max_retries)

    referer = Referer.objects.get(pk=referer_id)
    if blacklisted_url(referer.url):
        return

    r = requests.get(
        referer.url,
        headers={'User-Agent': "CourtListener"},
        verify=False,  # Integrity of a referer's referent is not important.
    )
    try:
        r.raise_for_status()
    except HTTPError as exc:
        if retried_exceeded:
            # We're not wanted here. Maybe we'll have better luck another time.
            return
        raise self.retry(exc=exc, countdown=countdown)

    html_tree = html.fromstring(r.text)
    try:
        title = getattr(html_tree.xpath('//title')[0], 'text', '')
        if title is not None:
            title = title.strip()
    except IndexError:
        title = ''

    if title:
        referer.page_title = trunc(
            title,
            referer._meta.get_field('page_title').max_length,
        )
        referer.save()

        if new_title_for_viz(referer):
            # Only send the email if we haven't seen this page title before for
            # this visualization.
            email = emails['referer_detected']
            email_body = email['body'] % (referer.url, referer.page_title, reverse(
                    'admin:visualizations_referer_change',
                    args=(referer.pk,)
            ))
            send_mail(email['subject'], email_body, email['from'],
                      email['to'])
    else:
        try:
            # Create an exception to catch.
            raise Exception("Couldn't get title from HTML")
        except Exception as exc:
            if retried_exceeded:
                # We couldn't get the title. Let it go.
                return
            raise self.retry(exc=exc, countdown=countdown)
