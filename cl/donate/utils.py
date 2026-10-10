from cl.donate.models import MembershipPaymentStatus


def map_payment_status_value(status: str) -> int:
    """
    Maps a payment status string into its corresponding
    integer value defined in the `MembershipPaymentStatus` class.

    An empty status means Neon attached no payment info to the membership.
    That happens for free tiers and for memberships granted manually in
    Neon, treat both as SUCCEEDED so they don't stick in "Awaiting payment
    processing".

    Args:
        status (str): The payment status string (e.g., "succeeded", "failed").

    Returns:
        int: The mapped constant value from `MembershipPaymentStatus`.
            Defaults to `PENDING` for unrecognized values.
    """
    match status:
        case "succeeded" | "":
            payment_status = MembershipPaymentStatus.SUCCEEDED
        case "failed":
            payment_status = MembershipPaymentStatus.FAILED
        case _:
            payment_status = MembershipPaymentStatus.PENDING

    return payment_status
