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

from alert.search.models import Court


class urlToHash(models.Model):
    '''A class to hold URLs and the hash of their contents. This could be added
    to the Court table, except that courts often have more than one URL they
    parse.
    '''
    hashUUID = models.AutoField("a unique ID for each hash/url pairing",
                                primary_key=True)
    url = models.CharField("the URL that is hashed",
                           max_length=300,
                           blank=True,
                           editable=False)
    SHA1 = models.CharField("a SHA1 of the court's website HTML",
                            max_length=40,
                            blank=True,
                            editable=False)

    def __unicode__(self):
        return self.url

    class Meta:
        db_table = "urlToHash"
        verbose_name = "URL Hash"
        verbose_name_plural = "URL Hashes"


class ErrorLog(models.Model):
    '''A class to hold scraper errors. Items are added by the scraper and
    removed by the scraper's status monitor.
    '''
    log_time = models.DateTimeField('the exact date and time of the error',
                                          auto_now_add=True,
                                          editable=False,
                                          null=True)
    log_level = models.CharField('the loglevel of the error encountered',
                                 max_length=15,
                                 editable=False)
    court = models.ForeignKey(Court,
                               verbose_name='the court where the document was filed')
    message = models.CharField('the message produced in the log',
                               max_length=400,
                               blank=True,
                               editable=False)

    def __unicode__(self):
        return "%s - %s@%s %s" % (self.time_retrieved,
                                    self.log_level,
                                    self.court.courtUUID,
                                    self.message)
