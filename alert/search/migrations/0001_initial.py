# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Court'
        db.create_table('Court', (
            ('courtUUID', self.gf('django.db.models.fields.CharField')(max_length=6, primary_key=True)),
            ('in_use', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('position', self.gf('django.db.models.fields.FloatField')(unique=True, null=True, db_index=True)),
            ('citation_string', self.gf('django.db.models.fields.CharField')(max_length=100, blank=True)),
            ('short_name', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('full_name', self.gf('django.db.models.fields.CharField')(max_length='200')),
            ('URL', self.gf('django.db.models.fields.URLField')(max_length=200)),
            ('start_date', self.gf('django.db.models.fields.DateField')(null=True, blank=True)),
            ('end_date', self.gf('django.db.models.fields.DateField')(null=True, blank=True)),
            ('jurisdiction', self.gf('django.db.models.fields.CharField')(max_length=3)),
        ))
        db.send_create_signal('search', ['Court'])

        # Adding model 'Citation'
        db.create_table('Citation', (
            ('citationUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('slug', self.gf('django.db.models.fields.SlugField')(max_length=50, null=True)),
            ('case_name', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('docketNumber', self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True)),
            ('westCite', self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True)),
            ('lexisCite', self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True)),
            ('neutral_cite', self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True)),
        ))
        db.send_create_signal('search', ['Citation'])

        # Adding model 'Document'
        db.create_table('Document', (
            ('documentUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('source', self.gf('django.db.models.fields.CharField')(max_length=3, blank=True)),
            ('documentSHA1', self.gf('django.db.models.fields.CharField')(max_length=40, db_index=True)),
            ('dateFiled', self.gf('django.db.models.fields.DateField')(db_index=True, null=True, blank=True)),
            ('court', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['search.Court'])),
            ('citation', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['search.Citation'], null=True, blank=True)),
            ('download_URL', self.gf('django.db.models.fields.URLField')(max_length=200, db_index=True)),
            ('time_retrieved', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, db_index=True, blank=True)),
            ('local_path', self.gf('django.db.models.fields.files.FileField')(db_index=True, max_length=100, blank=True)),
            ('documentPlainText', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('documentHTML', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('html_with_citations', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('citation_count', self.gf('django.db.models.fields.IntegerField')(default=0)),
            ('documentType', self.gf('django.db.models.fields.CharField')(max_length=50, blank=True)),
            ('date_blocked', self.gf('django.db.models.fields.DateField')(null=True, blank=True)),
            ('blocked', self.gf('django.db.models.fields.BooleanField')(default=False, db_index=True)),
            ('extracted_by_ocr', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal('search', ['Document'])

        # Adding M2M table for field cases_cited on 'Document'
        db.create_table('Document_cases_cited', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('document', models.ForeignKey(orm['search.document'], null=False)),
            ('citation', models.ForeignKey(orm['search.citation'], null=False))
        ))
        db.create_unique('Document_cases_cited', ['document_id', 'citation_id'])

    def backwards(self, orm):
        # Deleting model 'Court'
        db.delete_table('Court')

        # Deleting model 'Citation'
        db.delete_table('Citation')

        # Deleting model 'Document'
        db.delete_table('Document')

        # Removing M2M table for field cases_cited on 'Document'
        db.delete_table('Document_cases_cited')

    models = {
        'search.citation': {
            'Meta': {'object_name': 'Citation', 'db_table': "'Citation'"},
            'case_name': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'citationUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'docketNumber': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'lexisCite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'neutral_cite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True'}),
            'westCite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'})
        },
        'search.court': {
            'Meta': {'ordering': "['position']", 'object_name': 'Court', 'db_table': "'Court'"},
            'URL': ('django.db.models.fields.URLField', [], {'max_length': '200'}),
            'citation_string': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'courtUUID': ('django.db.models.fields.CharField', [], {'max_length': '6', 'primary_key': 'True'}),
            'end_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'full_name': ('django.db.models.fields.CharField', [], {'max_length': "'200'"}),
            'in_use': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'jurisdiction': ('django.db.models.fields.CharField', [], {'max_length': '3'}),
            'position': ('django.db.models.fields.FloatField', [], {'unique': 'True', 'null': 'True', 'db_index': 'True'}),
            'short_name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'start_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'})
        },
        'search.document': {
            'Meta': {'object_name': 'Document', 'db_table': "'Document'"},
            'blocked': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'cases_cited': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'citing_cases'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['search.Citation']"}),
            'citation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['search.Citation']", 'null': 'True', 'blank': 'True'}),
            'citation_count': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['search.Court']"}),
            'dateFiled': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_blocked': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'documentHTML': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentPlainText': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentSHA1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'documentType': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'documentUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'download_URL': ('django.db.models.fields.URLField', [], {'max_length': '200', 'db_index': 'True'}),
            'extracted_by_ocr': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'html_with_citations': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'local_path': ('django.db.models.fields.files.FileField', [], {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '3', 'blank': 'True'}),
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'})
        }
    }

    complete_apps = ['search']