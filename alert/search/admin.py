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

from alert.search.models import Citation
from alert.search.models import Court
from alert.search.models import Document

from django.contrib import admin

class DocumentAdminInline(admin.StackedInline):
    # ordering is brutal on MySQL. Don't put it here. Sorry.
    #list_display = ('citation',)
    #list_filter = ('court',)
    model = Document
    fields = ('citation', 'source', 'documentSHA1', 'dateFiled', 'court',
              'download_URL', 'local_path', 'documentPlainText', 'documentHTML',
              'documentType', 'blocked', 'date_blocked', 'extracted_by_ocr')
    raw_id_fields = ('citation',)
    search_fields = ['documentPlainText']


class CitationAdmin(admin.ModelAdmin):
    # This needs to be disabled for performance reasons.
    #list_display = ('docketNumber', 'westCite', 'case_name', )
    inlines = [DocumentAdminInline]
    search_fields = ['case_name', 'case_name', 'docketNumber', 'westCite']


class DocumentAdmin(admin.ModelAdmin):
    # ordering is brutal on MySQL. Don't put it here. Sorry.
    #list_display = ('citation',)
    #list_filter = ('court',)
    fields = ('source', 'documentSHA1', 'dateFiled', 'court',
              'download_URL', 'local_path', 'documentPlainText', 'documentHTML',
              'documentType', 'blocked', 'date_blocked', 'extracted_by_ocr')
    search_fields = ['documentPlainText']


class CourtAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'short_name', 'position', 'in_use')

admin.site.register(Document, DocumentAdmin)
admin.site.register(Court, CourtAdmin)
admin.site.register(Citation, CitationAdmin)

