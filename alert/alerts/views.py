from alert.userHandling.models import Alert

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.shortcuts import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext


@login_required
def edit_alert_redirect(request, alert_id):
    """Note that this method is still very useful because it gives people an
    opportunity to login if they come to the site via one of our email alerts.
    """
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
    return HttpResponseRedirect('/?%s&edit_alert=%s' % (alert.alertText, alert.pk))


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
