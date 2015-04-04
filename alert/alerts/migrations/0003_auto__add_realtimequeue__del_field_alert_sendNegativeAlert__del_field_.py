# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'RealTimeQueue'
        db.create_table(u'alerts_realtimequeue', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('date_modified', self.gf('django.db.models.fields.DateTimeField')(auto_now=True, db_index=True, blank=True)),
            ('item_type', self.gf('django.db.models.fields.CharField')(max_length=3, db_index=True)),
            ('item_pk', self.gf('django.db.models.fields.IntegerField')()),
        ))
        db.send_create_signal(u'alerts', ['RealTimeQueue'])

        # Renaming field 'Alert.sendNegativeAlert' to 'Alert.always_send_email'
        db.rename_column('Alert', 'sendNegativeAlert', 'always_send_email')

        # Renaming field 'Alert.alertText' to 'Alert.query'
        db.rename_column('Alert', 'alertText', 'query')

        # Renaming field 'Alert.lastHitDate' to 'Alert.date_last_hit'
        db.rename_column('Alert', 'lastHitDate', 'date_last_hit')

        # Renaming field 'Alert.alertFrequency' to 'Alert.rate'
        db.rename_column('Alert', 'alertFrequency', 'rate')

        # Renaming field 'Alert.alertName' to 'Alert.name'
        db.rename_column('Alert', 'alertName', 'name')

    def backwards(self, orm):
        db.delete_table(u'alerts_realtimequeue')
        db.rename_column('Alert', 'always_send_email', 'sendNegativeAlert')
        db.rename_column('Alert', 'query', 'alertText')
        db.rename_column('Alert', 'date_last_hit', 'lastHitDate')
        db.rename_column('Alert', 'rate', 'alertFrequency')
        db.rename_column('Alert', 'name', 'alertName')

    models = {
        u'alerts.alert': {
            'Meta': {'ordering': "['rate', 'query']", 'object_name': 'Alert', 'db_table': "'Alert'"},
            'always_send_email': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'date_last_hit': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '75'}),
            'query': ('django.db.models.fields.CharField', [], {'max_length': '2500'}),
            'rate': ('django.db.models.fields.CharField', [], {'max_length': '10'})
        },
        u'alerts.realtimequeue': {
            'Meta': {'object_name': 'RealTimeQueue'},
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'db_index': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'item_pk': ('django.db.models.fields.IntegerField', [], {}),
            'item_type': ('django.db.models.fields.CharField', [], {'max_length': '3', 'db_index': 'True'})
        }
    }

    complete_apps = ['alerts']
