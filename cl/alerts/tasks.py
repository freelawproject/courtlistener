import redis
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from django.utils.timezone import now

from cl.alerts.models import DocketAlert
from cl.celery import app
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.string_utils import trunc
from cl.search.models import Docket, DocketEntry
from cl.stats.utils import tally_stat


def make_alert_key(d_pk):
    return 'docket.alert.enqueued:%s' % d_pk


def enqueue_docket_alert(d_pk, since):
    """Enqueue a docket alert or punt it if there's already a task for it.

    :param d_pk: The ID of the docket we're going to send alerts for.
    :param since: We'll send alerts for any item that happened since this time.
    :return: True if we enqueued the item, false if not.
    """
    # Create an expiring semaphor in redis or check if there's already one
    # there.
    r = redis.StrictRedis(host=settings.REDIS_HOST,
                          port=settings.REDIS_PORT,
                          db=settings.REDIS_DATABASES['ALERTS'])
    key = make_alert_key(d_pk)
    currently_enqueued = bool(r.getset(key, True))
    if currently_enqueued:
        # We've got a task going for this alert.
        return False

    # We don't have a task for this yet. Set an expiration for the new key,
    # and make a new async task. The expiration gives us a safety so that the
    # semaphor *will* eventually go away even if our task or server crashes.
    safety_expiration_timeout = 10 * 60
    r.expire(key, safety_expiration_timeout)
    send_docket_alert.delay(d_pk, since)
    return True


@app.task
def send_docket_alert(d_pk, since):
    """Send an alert for a given docket

    :param d_pk: The docket PK that was modified
    :param since: If we run alerts, notify users about items *since* this time.
    :return: The dict that was passed in as data is simply passed through. The
    next task in the chain needs the same information.
    """
    docket = Docket.objects.get(pk=d_pk)
    new_des = DocketEntry.objects.filter(date_created__gte=since,
                                         docket=docket)
    email_addresses = User.objects.filter(
        docket_alerts__docket=docket,
    ).distinct().values_list('email', flat=True)

    if new_des.count() > 0 and email_addresses:
        # Notify every user that's subscribed to this alert.
        case_name = trunc(best_case_name(docket), 100, ellipsis='...')
        subject_template = loader.get_template('docket_alert_subject.txt')
        subject = subject_template.render({
            'docket': docket,
            'count': new_des.count(),
            'case_name': case_name,
        }).strip()  # Remove newlines that editors can insist on adding.
        email_context = {'new_des': new_des, 'docket': docket}
        txt_template = loader.get_template('docket_alert_email.txt')
        html_template = loader.get_template('docket_alert_email.html')
        msg = EmailMultiAlternatives(
            subject=subject,
            body=txt_template.render(email_context),
            from_email=settings.DEFAULT_ALERTS_EMAIL,
            bcc=email_addresses,
        )
        html = html_template.render(email_context)
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
        tally_stat('alerts.docket.alerts.sent', inc=len(email_addresses))

    DocketAlert.objects.filter(docket=docket).update(date_last_hit=now())

    # Work completed, clear the semaphor
    r = redis.StrictRedis(host=settings.REDIS_HOST,
                          port=settings.REDIS_PORT,
                          db=settings.REDIS_DATABASES['ALERTS'])
    r.delete(make_alert_key(d_pk))
