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

from django.db.models.signals import post_delete, post_save

from alert.search.models import Citation, Document
from alert.search.tasks import delete_doc_handler, save_doc_handler, save_cite_handler

post_save.connect(
            save_doc_handler,
            sender=Document,
            dispatch_uid='save_doc_handler')

post_delete.connect(
            delete_doc_handler,
            sender=Document,
            dispatch_uid='delete_doc_handler')

post_save.connect(
            save_cite_handler,
            sender=Citation,
            dispatch_uid='save_cite_handler')
