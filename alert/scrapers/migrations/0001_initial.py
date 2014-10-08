# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'urlToHash'
        db.create_table('urlToHash', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('url', self.gf('django.db.models.fields.CharField')(max_length=5000, blank=True)),
            ('SHA1', self.gf('django.db.models.fields.CharField')(max_length=40, blank=True)),
        ))
        db.send_create_signal(u'scrapers', ['urlToHash'])

        # Adding model 'ErrorLog'
        db.create_table(u'scrapers_errorlog', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('log_time', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, null=True, blank=True)),
            ('log_level', self.gf('django.db.models.fields.CharField')(max_length=15)),
            ('court', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['search.Court'])),
            ('message', self.gf('django.db.models.fields.TextField')(blank=True)),
        ))
        db.send_create_signal(u'scrapers', ['ErrorLog'])


    def backwards(self, orm):
        # Deleting model 'urlToHash'
        db.delete_table('urlToHash')

        # Deleting model 'ErrorLog'
        db.delete_table(u'scrapers_errorlog')


    models = {
        u'scrapers.errorlog': {
            'Meta': {'object_name': 'ErrorLog'},
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['search.Court']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'log_level': ('django.db.models.fields.CharField', [], {'max_length': '15'}),
            'log_time': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'null': 'True', 'blank': 'True'}),
            'message': ('django.db.models.fields.TextField', [], {'blank': 'True'})
        },
        u'scrapers.urltohash': {
            'Meta': {'object_name': 'urlToHash', 'db_table': "'urlToHash'"},
            'SHA1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'url': ('django.db.models.fields.CharField', [], {'max_length': '5000', 'blank': 'True'})
        },
        u'search.court': {
            'Meta': {'ordering': "['position']", 'object_name': 'Court', 'db_table': "'Court'"},
            'citation_string': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'null': 'True', 'db_index': 'True', 'blank': 'True'}),
            'end_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'full_name': ('django.db.models.fields.CharField', [], {'max_length': "'200'"}),
            'has_opinion_scraper': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'has_oral_argument_scraper': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'id': ('django.db.models.fields.CharField', [], {'max_length': '15', 'primary_key': 'True'}),
            'in_use': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'jurisdiction': ('django.db.models.fields.CharField', [], {'max_length': '3'}),
            'notes': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'position': ('django.db.models.fields.FloatField', [], {'unique': 'True', 'null': 'True', 'db_index': 'True'}),
            'short_name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'start_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'url': ('django.db.models.fields.URLField', [], {'max_length': '500'})
        }
    }

    complete_apps = ['scrapers']