from typing import Any

from celery import Task
from requests.exceptions import ConnectionError, Timeout
from zohocrmsdk.src.com.zoho.crm.api.record import Field
from zohocrmsdk.src.com.zoho.crm.api.util import Choice

from cl.celery_init import app
from cl.lib.command_utils import logger
from cl.lib.zoho import LeadsModule, ZohoDeskClient


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


@app.task(
    bind=True,
    autoretry_for=(Timeout,),
    max_retries=3,
    interval_start=5,
    ignore_result=True,
)
def create_zoho_crm_lead_from_contact(
    self: Task,
    *,
    name: str,
    email: str,
    message: str = "",
    partner_current_work: str = "",
    partner_prior_outreach: str = "",
    partner_team_size: str = "",
    partner_founded_year: int | None = None,
    partner_funding_total: str = "",
    partner_funding_stage: str = "",
    partner_ideal_outcome: str = "",
    partner_background: list[str] | None = None,
    partner_background_other: str = "",
) -> None:
    """Create a Lead in Zoho CRM from a partnership inquiry.

    :param name: Full name (split into first/last for CRM).
    :param email: Submitter's email.
    :param message: Optional message text.
    :param partner_current_work: What they're currently working on.
    :param partner_prior_outreach: Who they've contacted / what they've tried.
    :param partner_team_size: Human-readable team size label.
    :param partner_founded_year: Year the organization was founded.
    :param partner_funding_total: Human-readable funding total label.
    :param partner_funding_stage: Human-readable funding stage label.
    :param partner_ideal_outcome: What they want from connecting with us.
    :param partner_background: List of Human-readable background label(s).
    :param partner_background_other: User input "other" background.
    """
    parts = name.rsplit(" ", 1)
    first_name = parts[0] if len(parts) > 1 else ""
    last_name = parts[-1]

    # Build the "Have you raised funding?" custom field
    funding_parts: list[str] = []
    if partner_funding_total:
        funding_parts.append(
            "No"
            if partner_funding_total == "None"
            else f"Total: {partner_funding_total}"
        )
    if partner_funding_stage:
        funding_parts.append(f"VC funding status: {partner_funding_stage}")
    funding = "; ".join(funding_parts)

    # Build the "How long have you been working on this?" custom field
    how_long = (
        f"Founded {partner_founded_year}" if partner_founded_year else ""
    )

    # Build the "Anything else we should know?" custom field
    extras: list[str] = []
    if partner_background_other:
        extras.append(f"Background (other): {partner_background_other}")
    if partner_prior_outreach:
        extras.append(f"Prior outreach: {partner_prior_outreach}")
    if partner_ideal_outcome:
        extras.append(f"Ideal outcome: {partner_ideal_outcome}")
    if message:
        extras.append(f"Anything else: {message}")
    anything_else = "\n\n".join(extras)

    payload: dict[str, Any] = {
        Field.Leads.email(): email,
        Field.Leads.last_name(): last_name or "(unknown)",
        "What_are_you_working_on": partner_current_work,
        "How_big_is_your_team_and_organization": partner_team_size,
        "How_long_have_you_been_working_on_this": how_long,
        "Have_you_raised_funding": funding,
        "Anything_else_we_should_know": anything_else,
    }
    if first_name:
        payload[Field.Leads.first_name()] = first_name

    if partner_background:
        payload["Background"] = [
            Choice(background) for background in partner_background
        ]

    leads = LeadsModule()
    leads.create_record(payload)
    logger.info("Zoho CRM lead created for %s via contact form", email)
