# -*- coding: utf-8 -*-

from alert.alerts.forms import CreateAlertForm
from alert.userHandling.models import Alert

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.shortcuts import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext

@login_required
def edit_alert(request, alert_id):
    try:
        alert_id = int(alert_id)
    except ValueError:
        return HttpResponseRedirect('/')

    # check if the user can edit this, or if they are url hacking
    alert = get_object_or_404(
        Alert,
        pk=alert_id,
        userprofile=request.user.profile
    )

    # If they've made it this far, they can edit the item, therefore, we load
    # the form.
    if request.method == 'POST':
        alert_form = CreateAlertForm(request.POST)
        if alert_form.is_valid():
            cd = alert_form.cleaned_data

            # save the changes
            alert_form = CreateAlertForm(cd, instance=alert)
            alert_form.save() # this method saves it and returns it
            messages.add_message(
                request,
                messages.SUCCESS,
                'Your alert was saved successfully.'
            )

            # redirect to the alerts page
            return HttpResponseRedirect('/profile/alerts/')

    else:
        # the form is loading for the first time
        alert_form = CreateAlertForm(instance=alert)

    return render_to_response('profile/edit_alert.html',
                              {'form': alert_form, 'alert_id': alert_id,
                               'private': False},
                              RequestContext(request))

@login_required
def delete_alert(request, alert_id):
    try:
        alert_id = int(alert_id)
    except ValueError:
        return HttpResponseRedirect('/')

    # check if the user can edit this, or if they are url hacking
    alert = get_object_or_404(Alert, pk=alert_id,
                              userprofile=request.user.profile)

    # if they've made it this far, they have permission to edit the alert
    alert.delete()
    messages.add_message(request, messages.SUCCESS,
        'Your alert was deleted successfully.')
    return HttpResponseRedirect('/profile/alerts/')

@login_required
def delete_alert_confirm(request, alert_id):
    try:
        alert_id = int(alert_id)
    except ValueError:
        return HttpResponseRedirect('/')
    return render_to_response('profile/delete_confirm.html',
                              {'alert_id': alert_id, 'private': False},
                              RequestContext(request))
