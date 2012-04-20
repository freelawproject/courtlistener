# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Court'
        db.create_table('Court', (
            ('courtUUID', self.gf('django.db.models.fields.CharField')(max_length=100, primary_key=True)),
            ('URL', self.gf('django.db.models.fields.URLField')(max_length=200)),
            ('shortName', self.gf('django.db.models.fields.CharField')(max_length=100, blank=True)),
            ('startDate', self.gf('django.db.models.fields.DateField')(null=True, blank=True)),
            ('endDate', self.gf('django.db.models.fields.DateField')(null=True, blank=True)),
        ))
        db.send_create_signal('search', ['Court'])

        # Adding model 'Citation'
        db.create_table('Citation', (
            ('citationUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('slug', self.gf('django.db.models.fields.SlugField')(max_length=50, null=True)),
            ('caseNameShort', self.gf('django.db.models.fields.CharField')(db_index=True, max_length=100, blank=True)),
            ('caseNameFull', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('docketNumber', self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True)),
            ('westCite', self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True)),
            ('lexisCite', self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True)),
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
            ('time_retrieved', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, blank=True)),
            ('local_path', self.gf('django.db.models.fields.files.FileField')(max_length=100, blank=True)),
            ('documentPlainText', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('documentHTML', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('documentType', self.gf('django.db.models.fields.CharField')(max_length=50, blank=True)),
            ('date_blocked', self.gf('django.db.models.fields.DateField')(null=True, blank=True)),
            ('blocked', self.gf('django.db.models.fields.BooleanField')(default=False, db_index=True)),
        ))
        db.send_create_signal('search', ['Document'])

    def backwards(self, orm):
        # Deleting model 'Court'
        db.delete_table('Court')

        # Deleting model 'Citation'
        db.delete_table('Citation')

        # Deleting model 'Document'
        db.delete_table('Document')

    models = {
        'search.citation': {
            'Meta': {'object_name': 'Citation', 'db_table': "'Citation'"},
            'caseNameFull': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'caseNameShort': ('django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'citationUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'docketNumber': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'lexisCite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True'}),
            'westCite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'})
        },
        'search.court': {
            'Meta': {'ordering': "['courtUUID']", 'object_name': 'Court', 'db_table': "'Court'"},
            'URL': ('django.db.models.fields.URLField', [], {'max_length': '200'}),
            'courtUUID': ('django.db.models.fields.CharField', [], {'max_length': '100', 'primary_key': 'True'}),
            'endDate': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'shortName': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'startDate': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'})
        },
        'search.document': {
            'Meta': {'ordering': "['-time_retrieved']", 'object_name': 'Document', 'db_table': "'Document'"},
            'blocked': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'citation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['search.Citation']", 'null': 'True', 'blank': 'True'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['search.Court']"}),
            'dateFiled': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_blocked': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'documentHTML': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentPlainText': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentSHA1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'documentType': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'documentUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'download_URL': ('django.db.models.fields.URLField', [], {'max_length': '200', 'db_index': 'True'}),
            'local_path': ('django.db.models.fields.files.FileField', [], {'max_length': '100', 'blank': 'True'}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '3', 'blank': 'True'}),
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'})
        }
    }

    complete_apps = ['search']