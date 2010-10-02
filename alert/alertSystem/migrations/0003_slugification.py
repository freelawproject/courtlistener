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
# encoding: utf-8
import datetime
from south.db import db
from south.v2 import DataMigration
from django.db import models

class Migration(DataMigration):

    def forwards(self, orm):
        from django.template.defaultfilters import slugify
        for doc in orm.Document.objects.all():
            doc.url = slugify(doc.citation)
            doc.save()



    def backwards(self, orm):
        raise RuntimeError("Cannot reverse this migration.")


    models = {
        'alertSystem.citation': {
            'Meta': {'ordering': "['caseNameFull']", 'object_name': 'Citation', 'db_table': "'Citation'"},
            'caseNameFull': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'caseNameShort': ('django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'caseNumber': ('django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '50', 'blank': 'True'}),
            'citationUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'officialCitationLexis': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'officialCitationWest': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'})
        },
        'alertSystem.court': {
            'Meta': {'ordering': "['courtUUID']", 'object_name': 'Court', 'db_table': "'Court'"},
            'courtShortName': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'courtURL': ('django.db.models.fields.URLField', [], {'max_length': '200'}),
            'courtUUID': ('django.db.models.fields.CharField', [], {'max_length': '100', 'primary_key': 'True'})
        },
        'alertSystem.document': {
            'Meta': {'ordering': "['-time_retrieved']", 'object_name': 'Document', 'db_table': "'Document'"},
            'citation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.Citation']", 'null': 'True', 'blank': 'True'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.Court']"}),
            'dateFiled': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'documentHTML': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentPlainText': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentSHA1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'documentType': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'documentUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'download_URL': ('django.db.models.fields.URLField', [], {'max_length': '200'}),
            'excerptSummary': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.ExcerptSummary']", 'null': 'True', 'blank': 'True'}),
            'judge': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['alertSystem.Judge']", 'null': 'True', 'blank': 'True'}),
            'local_path': ('django.db.models.fields.files.FileField', [], {'max_length': '100', 'blank': 'True'}),
            'party': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['alertSystem.Party']", 'null': 'True', 'blank': 'True'}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '3', 'blank': 'True'}),
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'url': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True'})
        },
        'alertSystem.excerptsummary': {
            'Meta': {'object_name': 'ExcerptSummary', 'db_table': "'ExcerptSummary'"},
            'autoExcerpt': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'courtSummary': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'excerptUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'})
        },
        'alertSystem.judge': {
            'Meta': {'ordering': "['court', 'canonicalName']", 'object_name': 'Judge', 'db_table': "'Judge'"},
            'canonicalName': ('django.db.models.fields.CharField', [], {'max_length': '150'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.Court']"}),
            'endDate': ('django.db.models.fields.DateField', [], {}),
            'judgeAvatar': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'blank': 'True'}),
            'judgeUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'startDate': ('django.db.models.fields.DateField', [], {})
        },
        'alertSystem.judgealias': {
            'Meta': {'ordering': "['alias']", 'object_name': 'JudgeAlias', 'db_table': "'JudgeAlias'"},
            'alias': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'aliasUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'judgeUUID': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.Judge']"})
        },
        'alertSystem.party': {
            'Meta': {'ordering': "['partyExtracted']", 'object_name': 'Party', 'db_table': "'Party'"},
            'partyExtracted': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'partyUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'})
        },
        'alertSystem.urltohash': {
            'Meta': {'object_name': 'urlToHash', 'db_table': "'urlToHash'"},
            'SHA1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'blank': 'True'}),
            'hashUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'url': ('django.db.models.fields.CharField', [], {'max_length': '300', 'blank': 'True'})
        }
    }

    complete_apps = ['alertSystem']
