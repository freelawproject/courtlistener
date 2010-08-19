# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Adding model 'urlToHash'
        db.create_table('urlToHash', (
            ('hashUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('url', self.gf('django.db.models.fields.CharField')(max_length=300, blank=True)),
            ('SHA1', self.gf('django.db.models.fields.CharField')(max_length=40, blank=True)),
        ))
        db.send_create_signal('alertSystem', ['urlToHash'])

        # Adding model 'Court'
        db.create_table('Court', (
            ('courtUUID', self.gf('django.db.models.fields.CharField')(max_length=100, primary_key=True)),
            ('courtURL', self.gf('django.db.models.fields.URLField')(max_length=200)),
            ('courtShortName', self.gf('django.db.models.fields.CharField')(max_length=100, blank=True)),
        ))
        db.send_create_signal('alertSystem', ['Court'])

        # Adding model 'Party'
        db.create_table('Party', (
            ('partyUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('partyExtracted', self.gf('django.db.models.fields.CharField')(max_length=100)),
        ))
        db.send_create_signal('alertSystem', ['Party'])

        # Adding model 'Judge'
        db.create_table('Judge', (
            ('judgeUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('court', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['alertSystem.Court'])),
            ('canonicalName', self.gf('django.db.models.fields.CharField')(max_length=150)),
            ('judgeAvatar', self.gf('django.db.models.fields.files.ImageField')(max_length=100, blank=True)),
            ('startDate', self.gf('django.db.models.fields.DateField')()),
            ('endDate', self.gf('django.db.models.fields.DateField')()),
        ))
        db.send_create_signal('alertSystem', ['Judge'])

        # Adding model 'JudgeAlias'
        db.create_table('JudgeAlias', (
            ('aliasUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('judgeUUID', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['alertSystem.Judge'])),
            ('alias', self.gf('django.db.models.fields.CharField')(max_length=100)),
        ))
        db.send_create_signal('alertSystem', ['JudgeAlias'])

        # Adding model 'Citation'
        db.create_table('Citation', (
            ('citationUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('caseNameShort', self.gf('django.db.models.fields.CharField')(db_index=True, max_length=100, blank=True)),
            ('caseNameFull', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('caseNumber', self.gf('django.db.models.fields.CharField')(db_index=True, max_length=50, blank=True)),
            ('officialCitationWest', self.gf('django.db.models.fields.CharField')(max_length=50, blank=True)),
            ('officialCitationLexis', self.gf('django.db.models.fields.CharField')(max_length=50, blank=True)),
        ))
        db.send_create_signal('alertSystem', ['Citation'])

        # Adding model 'ExcerptSummary'
        db.create_table('ExcerptSummary', (
            ('excerptUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('autoExcerpt', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('courtSummary', self.gf('django.db.models.fields.TextField')(blank=True)),
        ))
        db.send_create_signal('alertSystem', ['ExcerptSummary'])

        # Adding model 'Document'
        db.create_table('Document', (
            ('documentUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('source', self.gf('django.db.models.fields.CharField')(max_length=3, blank=True)),
            ('documentSHA1', self.gf('django.db.models.fields.CharField')(max_length=40, db_index=True)),
            ('dateFiled', self.gf('django.db.models.fields.DateField')(db_index=True, null=True, blank=True)),
            ('court', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['alertSystem.Court'])),
            ('citation', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['alertSystem.Citation'], null=True, blank=True)),
            ('excerptSummary', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['alertSystem.ExcerptSummary'], null=True, blank=True)),
            ('download_URL', self.gf('django.db.models.fields.URLField')(max_length=200)),
            ('time_retrieved', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, blank=True)),
            ('local_path', self.gf('django.db.models.fields.files.FileField')(max_length=100, blank=True)),
            ('documentPlainText', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('documentHTML', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('documentType', self.gf('django.db.models.fields.CharField')(max_length=50, blank=True)),
        ))
        db.send_create_signal('alertSystem', ['Document'])

        # Adding M2M table for field judge on 'Document'
        db.create_table('Document_judge', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('document', models.ForeignKey(orm['alertSystem.document'], null=False)),
            ('judge', models.ForeignKey(orm['alertSystem.judge'], null=False))
        ))
        db.create_unique('Document_judge', ['document_id', 'judge_id'])

        # Adding M2M table for field party on 'Document'
        db.create_table('Document_party', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('document', models.ForeignKey(orm['alertSystem.document'], null=False)),
            ('party', models.ForeignKey(orm['alertSystem.party'], null=False))
        ))
        db.create_unique('Document_party', ['document_id', 'party_id'])


    def backwards(self, orm):
        
        # Deleting model 'urlToHash'
        db.delete_table('urlToHash')

        # Deleting model 'Court'
        db.delete_table('Court')

        # Deleting model 'Party'
        db.delete_table('Party')

        # Deleting model 'Judge'
        db.delete_table('Judge')

        # Deleting model 'JudgeAlias'
        db.delete_table('JudgeAlias')

        # Deleting model 'Citation'
        db.delete_table('Citation')

        # Deleting model 'ExcerptSummary'
        db.delete_table('ExcerptSummary')

        # Deleting model 'Document'
        db.delete_table('Document')

        # Removing M2M table for field judge on 'Document'
        db.delete_table('Document_judge')

        # Removing M2M table for field party on 'Document'
        db.delete_table('Document_party')


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
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'})
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
