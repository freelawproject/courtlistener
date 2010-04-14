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

from django.db import models

class alertsToSend(models.Model):
    alertUUID = models.AutoField("a unique ID for each alert", primary_key=True)
    user = models.ForeignKey(User,
        verbose_name="the user this model extends",
        unique=True)
    emailSubject = models.CharField("the subject of the email",
        max_length=200,
        blank=True)
    emailText = models.CharField("the text of the email",
        blank=True)
    
    def __unicode__(self):
        return self.emailSubject
    
    class Meta:
        verbose_name = "alert to send"
        verbose_name_plural = "Alerts to send"
        db_table = "AlertsToSend"
