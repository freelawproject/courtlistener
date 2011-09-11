# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Deleting model 'JudgeAlias'
        db.delete_table('JudgeAlias')

        # Deleting model 'ExcerptSummary'
        db.delete_table('ExcerptSummary')

        # Deleting model 'Judge'
        db.delete_table('Judge')

        # Deleting model 'Party'
        db.delete_table('Party')

        # Deleting field 'Document.excerptSummary'
        db.delete_column('Document', 'excerptSummary_id')

        # Adding field 'Document.blocked'
        db.add_column('Document', 'blocked', self.gf('django.db.models.fields.BooleanField')(default=False, blank=True), keep_default=False)

        # Removing M2M table for field judge on 'Document'
        db.delete_table('Document_judge')

        # Removing M2M table for field party on 'Document'
        db.delete_table('Document_party')

        # Removing index on 'Citation', fields ['slug']
        db.delete_index('Citation', ['slug'])


    def backwards(self, orm):
        
        # Adding model 'JudgeAlias'
        db.create_table('JudgeAlias', (
            ('alias', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('aliasUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('judgeUUID', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['alertSystem.Judge'])),
        ))
        db.send_create_signal('alertSystem', ['JudgeAlias'])

        # Adding model 'ExcerptSummary'
        db.create_table('ExcerptSummary', (
            ('excerptUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('courtSummary', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('autoExcerpt', self.gf('django.db.models.fields.TextField')(blank=True)),
        ))
        db.send_create_signal('alertSystem', ['ExcerptSummary'])

        # Adding model 'Judge'
        db.create_table('Judge', (
            ('judgeAvatar', self.gf('django.db.models.fields.files.ImageField')(max_length=100, blank=True)),
            ('endDate', self.gf('django.db.models.fields.DateField')()),
            ('startDate', self.gf('django.db.models.fields.DateField')()),
            ('canonicalName', self.gf('django.db.models.fields.CharField')(max_length=150)),
            ('court', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['alertSystem.Court'])),
            ('judgeUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
        ))
        db.send_create_signal('alertSystem', ['Judge'])

        # Adding model 'Party'
        db.create_table('Party', (
            ('partyExtracted', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('partyUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
        ))
        db.send_create_signal('alertSystem', ['Party'])

        # Adding field 'Document.excerptSummary'
        db.add_column('Document', 'excerptSummary', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['alertSystem.ExcerptSummary'], null=True, blank=True), keep_default=False)

        # Deleting field 'Document.blocked'
        db.delete_column('Document', 'blocked')

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

        # Adding index on 'Citation', fields ['slug']
        db.create_index('Citation', ['slug'])


    models = {
        'alertSystem.citation': {
            'Meta': {'object_name': 'Citation', 'db_table': "'Citation'"},
            'caseNameFull': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'caseNameShort': ('django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'citationUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'docketNumber': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'lexisCite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True'}),
            'westCite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'})
        },
        'alertSystem.court': {
            'Meta': {'ordering': "['courtUUID']", 'object_name': 'Court', 'db_table': "'Court'"},
            'URL': ('django.db.models.fields.URLField', [], {'max_length': '200'}),
            'courtUUID': ('django.db.models.fields.CharField', [], {'max_length': '100', 'primary_key': 'True'}),
            'endDate': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'shortName': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'startDate': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'})
        },
        'alertSystem.document': {
            'Meta': {'ordering': "['-time_retrieved']", 'object_name': 'Document', 'db_table': "'Document'"},
            'blocked': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'blank': 'True'}),
            'citation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.Citation']", 'null': 'True', 'blank': 'True'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.Court']"}),
            'dateFiled': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'documentHTML': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentPlainText': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentSHA1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'documentType': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'documentUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'download_URL': ('django.db.models.fields.URLField', [], {'max_length': '200'}),
            'local_path': ('django.db.models.fields.files.FileField', [], {'max_length': '100', 'blank': 'True'}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '3', 'blank': 'True'}),
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'})
        },
        'alertSystem.urltohash': {
            'Meta': {'object_name': 'urlToHash', 'db_table': "'urlToHash'"},
            'SHA1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'blank': 'True'}),
            'hashUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'url': ('django.db.models.fields.CharField', [], {'max_length': '300', 'blank': 'True'})
        }
    }

    complete_apps = ['alertSystem']
