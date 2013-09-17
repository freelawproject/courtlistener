from django.core.mail import send_mail
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext

from alert.contact.forms import ContactForm
from alert import settings
from alert.honeypot.decorators import check_honeypot

@check_honeypot(field_name='skip_me_if_alive')
def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data

            # pull the email addresses out of the MANAGERS tuple
            i = 0
            email_addresses = []
            while i < len(settings.MANAGERS):
                email_addresses.append(settings.MANAGERS[i][1])
                i += 1

            # send the email to the MANAGERS
            send_mail(
                'Message from %s at CourtListener.com: %s' % (cd['name'], cd['subject']),
                cd['message'],
                cd.get('email', 'noreply@example.com'),
                email_addresses,)
            # we must redirect after success to avoid problems with people using the refresh button.
            return HttpResponseRedirect('/contact/thanks/')
    else:
        # the form is loading for the first time
        try:
            email_addy = request.user.email
            full_name = request.user.get_full_name()
            form = ContactForm(
                initial={'name': full_name, 'email': email_addy}
            )
        except:
            # for anonymous users, who lack full_names, and emails
            form = ContactForm()

    return render_to_response('contact/contact_form.html',
                              {'form': form,
                               'private': False},
                              RequestContext(request))


def thanks(request):
    return render_to_response('contact/contact_thanks.html',
                              {'private': False},
                              RequestContext(request))
