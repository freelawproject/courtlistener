# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'ErrorLog'
        db.create_table('scrapers_errorlog', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('time_retrieved', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, db_index=True, blank=True)),
            ('log_level', self.gf('django.db.models.fields.CharField')(max_length=6)),
            ('court', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['search.Court'])),
            ('message', self.gf('django.db.models.fields.CharField')(max_length=400, blank=True)),
        ))
        db.send_create_signal('scrapers', ['ErrorLog'])

    def backwards(self, orm):
        # Deleting model 'ErrorLog'
        db.delete_table('scrapers_errorlog')

    models = {
        'scrapers.errorlog': {
            'Meta': {'object_name': 'ErrorLog'},
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['search.Court']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'log_level': ('django.db.models.fields.CharField', [], {'max_length': '6'}),
            'message': ('django.db.models.fields.CharField', [], {'max_length': '400', 'blank': 'True'}),
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'})
        },
        'scrapers.urltohash': {
            'Meta': {'object_name': 'urlToHash', 'db_table': "'urlToHash'"},
            'SHA1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'blank': 'True'}),
            'hashUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'url': ('django.db.models.fields.CharField', [], {'max_length': '300', 'blank': 'True'})
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
        }
    }

    complete_apps = ['scrapers']
