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


from django.contrib import admin
from alert.alertSystem.models import *

class DocumentAdminInline(admin.StackedInline):
    # ordering is brutal on MySQL. Don't put it here. Sorry.
    #list_display = ('citation',)
    #list_filter = ('court',)
    model = Document
    fields = ('citation', 'source', 'documentSHA1', 'dateFiled', 'court',
              'excerptSummary', 'download_URL',
              'local_path', 'documentPlainText', 'documentHTML',
              'documentType',)
    raw_id_fields = ('citation',)
    search_fields = ['documentPlainText']


class CitationAdmin(admin.ModelAdmin):
    # This needs to be disabled for performance reasons.
    #list_display = ('docketNumber', 'westCite', 'caseNameShort', )
    inlines = [DocumentAdminInline]
    search_fields = ['caseNameShort', 'caseNameFull', 'docketNumber', 'westCite']


admin.site.register(Court)
admin.site.register(Citation, CitationAdmin)

