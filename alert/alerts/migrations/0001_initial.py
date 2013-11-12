# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Alert'
        db.create_table('Alert', (
            ('alertUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('alertName', self.gf('django.db.models.fields.CharField')(max_length=75)),
            ('alertText', self.gf('django.db.models.fields.CharField')(max_length=2500)),
            ('alertFrequency', self.gf('django.db.models.fields.CharField')(max_length=10)),
            ('sendNegativeAlert', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('lastHitDate', self.gf('django.db.models.fields.DateTimeField')(null=True, blank=True)),
        ))
        db.send_create_signal('alerts', ['Alert'])

    def backwards(self, orm):
        # Deleting model 'Alert'
        db.delete_table('Alert')

    models = {
        'alerts.alert': {
            'Meta': {'ordering': "['alertFrequency', 'alertText']", 'object_name': 'Alert', 'db_table': "'Alert'"},
            'alertFrequency': ('django.db.models.fields.CharField', [], {'max_length': '10'}),
            'alertName': ('django.db.models.fields.CharField', [], {'max_length': '75'}),
            'alertText': ('django.db.models.fields.CharField', [], {'max_length': '2500'}),
            'alertUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lastHitDate': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'sendNegativeAlert': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        }
    }

    complete_apps = ['alerts']
