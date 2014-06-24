# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Audio'
        db.create_table(u'audio_audio', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('docket', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='oral_arguments', null=True, to=orm['search.Docket'])),
            ('time_retrieved', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, db_index=True, blank=True)),
            ('date_modified', self.gf('django.db.models.fields.DateTimeField')(auto_now=True, null=True, db_index=True, blank=True)),
            ('date_argued', self.gf('django.db.models.fields.DateField')(null=True, blank=True)),
            ('sha1', self.gf('django.db.models.fields.CharField')(max_length=40, db_index=True)),
            ('download_url', self.gf('django.db.models.fields.URLField')(db_index=True, max_length=500, null=True, blank=True)),
            ('local_path_mp3', self.gf('django.db.models.fields.files.FileField')(db_index=True, max_length=100, blank=True)),
            ('length', self.gf('django.db.models.fields.SmallIntegerField')()),
            ('date_blocked', self.gf('django.db.models.fields.DateField')(db_index=True, null=True, blank=True)),
            ('blocked', self.gf('django.db.models.fields.BooleanField')(default=False, db_index=True)),
        ))
        db.send_create_signal(u'audio', ['Audio'])


    def backwards(self, orm):
        # Deleting model 'Audio'
        db.delete_table(u'audio_audio')


    models = {
        u'audio.audio': {
            'Meta': {'ordering': "['-time_retrieved']", 'object_name': 'Audio'},
            'blocked': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'date_argued': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'date_blocked': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'null': 'True', 'db_index': 'True', 'blank': 'True'}),
            'docket': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'oral_arguments'", 'null': 'True', 'to': u"orm['search.Docket']"}),
            'download_url': ('django.db.models.fields.URLField', [], {'db_index': 'True', 'max_length': '500', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'length': ('django.db.models.fields.SmallIntegerField', [], {}),
            'local_path_mp3': ('django.db.models.fields.files.FileField', [], {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'sha1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'})
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
        },
        u'search.docket': {
            'Meta': {'object_name': 'Docket'},
            'case_name': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['search.Court']", 'null': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'null': 'True', 'db_index': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True'})
        }
    }

    complete_apps = ['audio']