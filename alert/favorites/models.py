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

from django.core.validators import MaxLengthValidator
from django.db import models
from alert.search.models import Document

# a class where favorites are held
class Favorite(models.Model):
    doc_id = models.ForeignKey(Document,
        verbose_name='the document that is favorited')
    name = models.CharField('a name for the alert', max_length=100)
    notes = models.TextField('notes about the favorite',
        validators=[MaxLengthValidator(500)],
        max_length=500,
        blank=True)
    def __unicode__(self):
        return 'Favorite %s' % self.id

    class Meta:
        db_table = 'Favorite'
