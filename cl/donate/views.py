import logging
from typing import Dict, Tuple, Union

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils.timezone import now
from stripe.stripe_object import StripeObject

from cl.donate.forms import (
    CleanedDonationFormType,
    CleanedUserFormType,
    DonationForm,
    ProfileForm,
    UserForm,
)
from cl.donate.models import (
    FREQUENCIES,
    PAYMENT_TYPES,
    PROVIDERS,
    Donation,
    MonthlyDonation,
)
from cl.donate.paypal import process_paypal_payment
from cl.donate.stripe_helpers import (
    create_stripe_customer,
    process_stripe_payment,
)
from cl.donate.utils import PaymentFailureException, send_thank_you_email
from cl.lib.http import is_ajax
from cl.lib.ratelimiter import ratelimiter_unsafe_10_per_m
from cl.users.utils import create_stub_account

logger = logging.getLogger(__name__)


def route_and_process_payment(
    request: HttpRequest,
    cd_donation_form: CleanedDonationFormType,
    cd_user_form: CleanedUserFormType,
    payment_provider: str,
    frequency: str,
    stripe_redirect_url: str,
    payment_type: str,
) -> Tuple[HttpResponse, StripeObject]:
    """Routes the donation to the correct payment provider, then normalizes
    its response.


    :param request: The WSGI request from Django
    :param cd_donation_form: The donation form with cleaned data
    :param cd_user_form: The user form with cleaned data
    :param payment_provider: The payment provider for the payment
    :param frequency: Whether monthly or one-time payment/donation
    :param stripe_redirect_url: Where to redirect a stripe payment after
    success
    :param payment_type: Whether it's a donation or payment

    Returns a dict with:
     - message: Any error messages that apply
     - status: The status of the payment for the database
     - payment_id: The ID of the payment
    """
    customer = None
    if payment_provider == PROVIDERS.PAYPAL:
        response = process_paypal_payment(cd_donation_form)
    elif payment_provider == PROVIDERS.CREDIT_CARD:
        stripe_token = request.POST.get("stripeToken")
        stripe_args = {"metadata": {"type": payment_type}}
        if frequency == FREQUENCIES.ONCE:
            stripe_args["card"] = stripe_token
        elif frequency == FREQUENCIES.MONTHLY:
            customer = create_stripe_customer(
                stripe_token, cd_user_form["email"]
            )
            stripe_args["customer"] = customer.id
            stripe_args["metadata"].update({"recurring": True})
        else:
            raise NotImplementedError(f"Unknown frequency value: {frequency}")

        if cd_donation_form["reference"]:
            stripe_args["metadata"].update(
                {"reference": cd_donation_form["reference"]}
            )

        # Calculate the amount in cents
        amount = int(float(cd_donation_form["amount"]) * 100)
        response = process_stripe_payment(
            amount, cd_user_form["email"], stripe_args, stripe_redirect_url
        )
    else:
        raise PaymentFailureException("Unknown/unhandled payment provider.")

    return response, customer


def add_monthly_donations(
    cd_donation_form: CleanedDonationFormType,
    user: User,
    customer: StripeObject,
) -> None:
    """Sets things up for monthly donations to run properly."""
    monthly_donation = MonthlyDonation(
        donor=user,
        enabled=True,
        monthly_donation_amount=cd_donation_form["amount"],
        monthly_donation_day=min(now().date().day, 28),
    )
    monthly_donation.payment_provider = PROVIDERS.CREDIT_CARD
    monthly_donation.stripe_customer_id = customer.id
    monthly_donation.save()


PaymentContext = Dict[
    str,
    Union[DonationForm, UserForm, ProfileForm, str, bool],
]


def make_payment_page_context(
    request: HttpRequest,
) -> PaymentContext:
    """Load the donate page or process a submitted donation.

    This page has several branches. The logic is as follows:
        if GET:
            --> Load the page
        elif POST:
            if user is anonymous:
                if email address on record as a stub account:
                    --> Use it.
                elif new email address or a non-stub account:
                    --> We cannot allow anonymous people to update real
                        accounts, or this is a new email address, so create a
                        new stub account.
            elif user is logged in:
                --> associate with account.

            We now have an account. Process the payment and associate it.
    """
    stub_account = False
    if request.method == "POST":
        donation_form = DonationForm(request.POST)

        if request.user.is_anonymous:
            # Either this is a new account, a stubbed one, or a user that's
            # simply not logged into their account
            try:
                stub_account = User.objects.filter(
                    profile__stub_account=True
                ).get(email__iexact=request.POST.get("email"))
            except User.DoesNotExist:
                # Either a regular account or an email address we've never
                # seen before. Create a new user from the POST data.
                user_form = UserForm(request.POST)
                profile_form = ProfileForm(request.POST)
            else:
                # We use the stub account and anonymous users even are allowed
                # to update it. This is OK, because we don't care too much
                # about the accuracy of this data. Later if/when this becomes
                # a real account, anonymous users won't be able to update this
                # information -- that's what matters.
                user_form = UserForm(request.POST, instance=stub_account)
                profile_form = ProfileForm(
                    request.POST, instance=stub_account.profile
                )

        else:
            user_form = UserForm(request.POST, instance=request.user)
            profile_form = ProfileForm(
                request.POST, instance=request.user.profile
            )
    else:
        # Loading the page...
        donation_form = DonationForm(
            initial={
                "referrer": request.GET.get("referrer"),
                "reference": request.GET.get("reference"),
                "amount": request.GET.get("amount"),
                "amount_other": request.GET.get("amount_other"),
            }
        )
        try:
            user_form = UserForm(
                initial={
                    "first_name": request.user.first_name,
                    "last_name": request.user.last_name,
                    "email": request.user.email,
                }
            )
            up = request.user.profile
            profile_form = ProfileForm(
                initial={
                    "address1": up.address1,
                    "address2": up.address2,
                    "city": up.city,
                    "state": up.state,
                    "zip_code": up.zip_code,
                    "wants_newsletter": up.wants_newsletter,
                }
            )
        except AttributeError:
            # for anonymous users, who lack profile info
            user_form = UserForm()
            profile_form = ProfileForm()

    return {
        "donation_form": donation_form,
        "user_form": user_form,
        "profile_form": profile_form,
        "stripe_public_key": settings.STRIPE_PUBLIC_KEY,
        "stub_account": stub_account,
    }


def process_donation_forms(
    request: HttpRequest,
    template_name: str,
    stripe_redirect_url: str,
    context: PaymentContext,
    payment_type: str,
) -> Union[HttpResponseRedirect, HttpResponse]:
    donation_form = context["donation_form"]
    user_form = context["user_form"]
    profile_form = context["profile_form"]
    if all(
        [
            donation_form.is_valid(),
            user_form.is_valid(),
            profile_form.is_valid(),
        ]
    ):
        # Process the data in form.cleaned_data
        cd_donation_form = donation_form.cleaned_data
        cd_user_form = user_form.cleaned_data
        cd_profile_form = profile_form.cleaned_data
        frequency = request.POST.get("frequency")

        # Route the payment to a payment provider
        payment_provider = cd_donation_form["payment_provider"]
        try:
            response, customer = route_and_process_payment(
                request,
                cd_donation_form,
                cd_user_form,
                payment_provider,
                frequency,
                stripe_redirect_url,
                payment_type,
            )
        except PaymentFailureException as e:
            logger.info("Payment failed. Message was: %s", e)
            context["message"] = str(e)
            response = {"status": "Failed"}

        logger.info("Payment routed with response: %s", response)
        if response["status"] == Donation.AWAITING_PAYMENT:
            if request.user.is_anonymous and not context["stub_account"]:
                # Create a stub account with an unusable password
                user, profile = create_stub_account(
                    cd_user_form, cd_profile_form
                )
                user.save()
                profile.save()
            else:
                # Logged in user or an existing stub account.
                user = user_form.save()
                profile_form.save()

            donation = donation_form.save(commit=False)
            donation.status = response["status"]
            donation.payment_id = response["payment_id"]
            # Will only work for Paypal:
            donation.transaction_id = response.get("transaction_id")
            donation.donor = user
            donation.save()

            if frequency == FREQUENCIES.MONTHLY and customer:
                add_monthly_donations(cd_donation_form, user, customer)

            return HttpResponseRedirect(response["redirect"])

    return render(request, template_name, context)


@ratelimiter_unsafe_10_per_m
def donate(request: HttpRequest) -> Union[HttpResponseRedirect, HttpResponse]:
    context = make_payment_page_context(request)
    context["private"] = False
    return process_donation_forms(
        request,
        template_name="donate.html",
        stripe_redirect_url=reverse("donate_complete"),
        context=context,
        payment_type=PAYMENT_TYPES.DONATION,
    )


@ratelimiter_unsafe_10_per_m
def badge_signup(
    request: HttpRequest,
) -> Union[HttpResponseRedirect, HttpResponse]:
    context = make_payment_page_context(request)
    context["private"] = True
    return process_donation_forms(
        request,
        template_name="badge_signup.html",
        stripe_redirect_url=reverse("badge_signup_complete"),
        context=context,
        payment_type=PAYMENT_TYPES.BADGE_SIGNUP,
    )


def payment_complete(
    request: HttpRequest,
    template_name: str,
) -> HttpResponse:
    error = None
    if len(request.GET) > 0:
        # We've gotten some information from the payment provider
        if request.GET.get("error") == "failure":
            error_msg = request.GET.get("error_description", "").lower()
            if error_msg == "user cancelled":
                error = "user_cancelled"
            elif "insufficient funds" in error_msg:
                error = "insufficient_funds"
            return render(
                request,
                "donate_complete.html",
                {"error": error, "private": True},
            )

    return render(
        request,
        template_name,
        {"error": error, "private": True},
    )


def toggle_monthly_donation(request: HttpRequest) -> HttpResponse:
    """Use Ajax to enable/disable monthly contributions"""
    if is_ajax(request) and request.method == "POST":
        monthly_pk = request.POST.get("id")
        m_donation = MonthlyDonation.objects.get(pk=monthly_pk)
        state = m_donation.enabled
        if state:
            m_donation.enabled = False
            msg = "Monthly contribution disabled successfully"
        else:
            m_donation.enabled = True
            msg = "Monthly contribution enabled successfully"
        m_donation.save()
        return HttpResponse(msg)
    else:
        return HttpResponseNotAllowed(
            permitted_methods={"POST"}, content="Not an Ajax POST request."
        )


@staff_member_required
def make_check_donation(request: HttpRequest) -> HttpResponse:
    """A page for admins to use to input check donations manually."""
    if request.method == "POST":
        data = request.POST.copy()
        data.update({"payment_provider": PROVIDERS.CHECK, "amount": "other"})
        donation_form = DonationForm(data)
        # Get the user, if we can. Else, set up the form to create a new user.
        try:
            email = request.POST.get("email").strip()
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            user = None
            user_form = UserForm(request.POST)
            profile_form = ProfileForm(request.POST)
        else:
            user_form = UserForm(request.POST, instance=user)
            profile_form = ProfileForm(request.POST, instance=user.profile)

        if all(
            [
                donation_form.is_valid(),
                user_form.is_valid(),
                profile_form.is_valid(),
            ]
        ):
            cd_user_form = user_form.cleaned_data
            cd_profile_form = profile_form.cleaned_data
            if user is not None:
                user = user_form.save()
                profile_form.save()
            else:
                user, profile = create_stub_account(
                    cd_user_form, cd_profile_form
                )
                user.save()
                profile.save()

            d = donation_form.save(commit=False)
            d.status = Donation.PROCESSED
            d.donor = user
            d.save()
            if user.email:
                send_thank_you_email(d, PAYMENT_TYPES.DONATION)

            return HttpResponseRedirect(reverse("donate_complete"))
    else:
        donation_form = DonationForm()
        user_form = UserForm()
        profile_form = ProfileForm()

    return render(
        request,
        "check_donation.html",
        {
            "donation_form": donation_form,
            "profile_form": profile_form,
            "user_form": user_form,
            "private": True,
        },
    )
