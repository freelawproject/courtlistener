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

FREQUENCY = (
    ('dly', 'Daily'),
    ('wly', 'Weekly'),
    ('mly', 'Monthly'),
    ('off', 'Off'),
)

# a class where alerts are held/handled.
class Alert(models.Model):
    alertUUID = models.AutoField('a unique ID for each alert', primary_key=True)
    alertName = models.CharField('a name for the alert', max_length=75)
    alertText = models.CharField('the text of an alert created by a user',
        max_length=200)
    alertFrequency = models.CharField('the rate chosen by the user for the alert',
        choices=FREQUENCY,
        max_length=10)
    alertPrivacy = models.BooleanField('should the alert be considered private',
        default=True)
    sendNegativeAlert = models.BooleanField('should alerts be sent when there are no hits during a specified period',
        default=False)
    lastHitDate = models.DateTimeField('the exact date and time stamp that the alert last sent an email',
        blank=True,
        null=True)

    def __unicode__(self):
        return 'Alert ' + str(self.alertUUID) + ': ' + self.alertText

    class Meta:
        verbose_name = 'alert'
        ordering = [ 'alertFrequency', 'alertText']
        db_table = 'Alert'
