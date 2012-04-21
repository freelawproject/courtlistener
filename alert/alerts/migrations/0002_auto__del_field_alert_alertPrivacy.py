# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Deleting field 'Alert.alertPrivacy'
        db.delete_column('Alert', 'alertPrivacy')

    def backwards(self, orm):
        # Adding field 'Alert.alertPrivacy'
        db.add_column('Alert', 'alertPrivacy',
                      self.gf('django.db.models.fields.BooleanField')(default=True),
                      keep_default=False)

    models = {
        'alerts.alert': {
            'Meta': {'ordering': "['alertFrequency', 'alertText']", 'object_name': 'Alert', 'db_table': "'Alert'"},
            'alertFrequency': ('django.db.models.fields.CharField', [], {'max_length': '10'}),
            'alertName': ('django.db.models.fields.CharField', [], {'max_length': '75'}),
            'alertText': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'alertUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lastHitDate': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'sendNegativeAlert': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        }
    }

    complete_apps = ['alerts']