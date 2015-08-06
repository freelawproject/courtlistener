# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Deleting field 'Audio.date_argued'
        db.delete_column(u'audio_audio', 'date_argued')

        # Deleting field 'Audio.docket_number'
        db.delete_column(u'audio_audio', 'docket_number')


    def backwards(self, orm):
        # Adding field 'Audio.date_argued'
        db.add_column(u'audio_audio', 'date_argued',
                      self.gf('django.db.models.fields.DateField')(blank=True, null=True, db_index=True),
                      keep_default=False)

        # Adding field 'Audio.docket_number'
        db.add_column(u'audio_audio', 'docket_number',
                      self.gf('django.db.models.fields.CharField')(max_length=5000, null=True, blank=True),
                      keep_default=False)


    models = {
        u'audio.audio': {
            'Meta': {'ordering': "['-time_retrieved']", 'object_name': 'Audio'},
            'blocked': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'case_name': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'date_blocked': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'db_index': 'True', 'blank': 'True'}),
            'docket': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'audio_files'", 'null': 'True', 'to': u"orm['search.Docket']"}),
            'download_url': ('django.db.models.fields.URLField', [], {'db_index': 'True', 'max_length': '500', 'null': 'True', 'blank': 'True'}),
            'duration': ('django.db.models.fields.SmallIntegerField', [], {'null': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'judges': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'local_path_mp3': ('django.db.models.fields.files.FileField', [], {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'local_path_original_file': ('django.db.models.fields.files.FileField', [], {'max_length': '100', 'db_index': 'True'}),
            'processing_complete': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'sha1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '3', 'blank': 'True'}),
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
            'blocked': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'case_name': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'case_name_full': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['search.Court']", 'null': 'True'}),
            'date_argued': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_blocked': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'null': 'True', 'db_index': 'True', 'blank': 'True'}),
            'date_reargued': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'docket_number': ('django.db.models.fields.CharField', [], {'max_length': '5000', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True'})
        }
    }

    complete_apps = ['audio']