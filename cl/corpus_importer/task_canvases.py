"""A place where we can put higher-level task canvases and methods.

This should help us organize the kinds of things we routinely do.
"""
from celery import chain
from django.contrib.auth.models import User

from cl.corpus_importer.tasks import get_attachment_page_by_rd, \
    make_attachment_pq_object, get_docket_by_pacer_case_id, \
    get_pacer_case_id_and_title, get_bankr_claims_registry
from cl.lib.celery_utils import CeleryThrottle
from cl.recap.tasks import process_recap_attachment
from cl.search.tasks import add_or_update_recap_docket


def get_docket_and_claims(docket_number, court, case_name, cookies, tags, q):
    """Get the docket report, claims history report, and save it all to the DB
     and Solr
    """
    chain(
        get_pacer_case_id_and_title.s(
            pass_through=None,
            docket_number=docket_number,
            court_id=court,
            cookies=cookies,
            case_name=case_name,
            docket_number_letters='bk',
        ).set(queue=q),
        get_docket_by_pacer_case_id.s(
            court_id=court,
            cookies=cookies,
            tag_names=tags,
            **{
                'show_parties_and_counsel': True,
                'show_terminated_parties': True,
                'show_list_of_member_cases': False,
            }
        ).set(queue=q),
        get_bankr_claims_registry.s(
            cookies=cookies,
            tag_names=tags,
        ).set(queue=q),
        add_or_update_recap_docket.s().set(queue=q),
    ).apply_async()


def get_district_attachment_pages(options, rd_pks, tag_names, session):
    """Get the attachment page information for all of the items selected

    :param options: The options returned by argparse. Should have the following
    keys:
     - queue: The celery queue to use
     - offset: The offset to skip
     - limit: The limit to stop after
    :param rd_pks: A list or ValuesList of RECAPDocument PKs to get attachment
    pages for.
    :param tag_names: A list of tags to associate with the downloaded items.
    :param session: A PACER logged-in PacerSession object
    :return None
    """
    q = options['queue']
    recap_user = User.objects.get(username='recap')
    throttle = CeleryThrottle(queue_name=q)
    for i, rd_pk in enumerate(rd_pks):
        if i < options['offset']:
            continue
        if i >= options['limit'] > 0:
            break
        throttle.maybe_wait()
        chain(
            get_attachment_page_by_rd.s(rd_pk, session.cookies).set(queue=q),
            make_attachment_pq_object.s(rd_pk, recap_user.pk).set(queue=q),
            process_recap_attachment.s(tag_names=tag_names).set(queue=q),
        ).apply_async()
