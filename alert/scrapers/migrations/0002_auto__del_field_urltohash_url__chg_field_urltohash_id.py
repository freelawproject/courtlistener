# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Deleting field 'urlToHash.url'
        db.delete_column('urlToHash', 'url')
        db.rename_column('urlToHash', 'hashUUID', 'id')


        # Changing field 'urlToHash.id'
        db.alter_column('urlToHash', 'id', self.gf('django.db.models.fields.CharField')(max_length=5000, primary_key=True))

    def backwards(self, orm):
        # Adding field 'urlToHash.url'
        db.add_column('urlToHash', 'url',
                      self.gf('django.db.models.fields.CharField')(default='', max_length=5000, blank=True),
                      keep_default=False)


        # Changing field 'urlToHash.id'
        db.alter_column('urlToHash', u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True))

        db.rename_column('urlToHash', 'id', 'hashUUID')

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
            'id': ('django.db.models.fields.CharField', [], {'max_length': '5000', 'primary_key': 'True'})
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
