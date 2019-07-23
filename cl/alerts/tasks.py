import redis
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives, get_connection
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


def enqueue_docket_alert(d_pk):
    """Enqueue a docket alert or punt it if there's already a task for it.

    :param d_pk: The ID of the docket we're going to send alerts for.
    :return: True if we enqueued the item, false if not.
    """
    # Create an expiring semaphor in redis or check if there's already one
    # there.
    r = redis.StrictRedis(host=settings.REDIS_HOST,
                          port=settings.REDIS_PORT,
                          db=settings.REDIS_DATABASES['ALERTS'])
    key = make_alert_key(d_pk)
    # Set to True if not already set. Redis doesn't do bools anymore, so use 1.
    currently_enqueued = bool(r.getset(key, 1))
    if currently_enqueued:
        # We've got a task going for this alert.
        return False

    # We don't have a task for this yet. Set an expiration for the new key,
    # and make a new async task. The expiration gives us a safety so that the
    # semaphor *will* eventually go away even if our task or server crashes.
    safety_expiration_timeout = 10 * 60
    r.expire(key, safety_expiration_timeout)
    return True


# Ignore the result or else we'll use a lot of memory.
@app.task(ignore_result=True)
def send_docket_alert(d_pk, since):
    """Send an alert for a given docket

    :param d_pk: The docket PK that was modified
    :param since: If we run alerts, notify users about items *since* this time.
    :return: None
    """
    email_addresses = User.objects.filter(
        docket_alerts__docket_id=d_pk,
    ).distinct().values_list('email', flat=True)
    if email_addresses:
        # We have an alert for this docket. Proceed.
        docket = Docket.objects.get(pk=d_pk)
        new_des = DocketEntry.objects.filter(date_created__gte=since,
                                             docket=docket)

        if new_des.count() > 0:
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
            messages = []
            for email_address in email_addresses:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=txt_template.render(email_context),
                    from_email=settings.DEFAULT_ALERTS_EMAIL,
                    to=[email_address],
                    headers={'X-Entity-Ref-ID': 'docket.alert:%s' % d_pk}
                )
                html = html_template.render(email_context)
                msg.attach_alternative(html, "text/html")
                messages.append(msg)

            # Add a bcc to the first message in the list so that we get a copy.
            messages[0].bcc = ['docket-alert-testing@free.law']
            connection = get_connection()
            connection.send_messages(messages)
            tally_stat('alerts.docket.alerts.sent', inc=len(email_addresses))

        DocketAlert.objects.filter(docket=docket).update(date_last_hit=now())

    # Work completed, clear the semaphor
    r = redis.StrictRedis(host=settings.REDIS_HOST,
                          port=settings.REDIS_PORT,
                          db=settings.REDIS_DATABASES['ALERTS'])
    r.delete(make_alert_key(d_pk))


@app.task(ignore_result=True)
def send_docket_alerts(data):
    """Send many docket alerts at one time without making numerous calls
    to the send_docket_alert function.

    :param data: A dict with up to two keys:

      d_pks_to_alert: A list of tuples. Each tuple contains the docket ID, and
                      a time. The time indicates that alerts should be sent for
                      items *after* that point.
        rds_for_solr: A list of RECAPDocument ids that need to be sent to Solr
                      to be made searchable.
    :returns: Simply passes through the rds_for_solr list, in case it is
    consumed by the next task. If rds_for_solr is not provided, returns an
    empty list.
    """
    for args in data['d_pks_to_alert']:
        send_docket_alert(*args)

    return data.get('rds_for_solr', [])
