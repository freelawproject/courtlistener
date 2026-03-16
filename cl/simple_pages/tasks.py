from celery import Task
from requests.exceptions import ConnectionError, Timeout

from cl.celery_init import app
from cl.lib.zoho import ZohoDeskClient


@app.task(
    bind=True,
    autoretry_for=(Timeout, ConnectionError),
    max_retries=3,
    interval_start=5,
    ignore_result=True,
)
def create_zoho_desk_ticket(
    self: Task,
    *,
    subject: str,
    name: str,
    email: str,
    description: str,
    request_type: str,
    assignee_id: str = "",
) -> None:
    """Create a ticket in Zoho Desk from a contact form submission.

    :param subject: User-provided subject line.
    :param name: Submitter's full name.
    :param email: Submitter's email address.
    :param description: Full rendered body of the form submission.
    :param request_type: Category label (e.g. "General Support",
        "Sealing Order").
    :param assignee_id: Zoho Desk agent ID, or empty for unassigned.
    """
    client = ZohoDeskClient()
    client.create_ticket(
        subject=subject,
        email=email,
        contact_name=name,
        description=description,
        request_type=request_type,
        assignee_id=assignee_id,
    )
