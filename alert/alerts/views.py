# -*- coding: utf-8 -*-
# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.

from alert.search.forms import CreateAlertForm
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
    alert = get_object_or_404(Alert, pk=alert_id,
                              users__user=request.user)

    # If they've made it this far, they can edit the item, therefore, we load 
    # the form.
    if request.method == 'POST':
        form = CreateAlertForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data

            # save the changes
            alert_form = CreateAlertForm(cd, instance=alert)
            alert_form.save() # this method saves it and returns it
            messages.add_message(request, messages.SUCCESS,
                'Your alert was saved successfully.')

            # redirect to the alerts page
            return HttpResponseRedirect('/profile/alerts/')

        else:
            # the form is loading for the first time
            alert_form = CreateAlertForm(instance=alert)

        return render_to_response('profile/edit_alert.html',
                                  {'form': alert_form, 'alert_id': alert_id},
                                  RequestContext(request))


@login_required
def delete_alert(request, alert_id):
    try:
        alert_id = int(alert_id)
    except ValueError:
        return HttpResponseRedirect('/')

    # check if the user can edit this, or if they are url hacking
    alert = get_object_or_404(Alert, pk=alert_id,
                              users__user=request.user)

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
                              {'alert_id': alert_id}, RequestContext(request))
