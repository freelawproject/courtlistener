# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Donation'
        db.create_table('donate_donation', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('date_modified', self.gf('django.db.models.fields.DateTimeField')(auto_now=True, db_index=True, blank=True)),
            ('date_created', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, db_index=True, blank=True)),
            ('clearing_date', self.gf('django.db.models.fields.DateTimeField')(null=True, blank=True)),
            ('send_annual_reminder', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('amount', self.gf('django.db.models.fields.DecimalField')(default=None, max_digits=10, decimal_places=2)),
            ('payment_provider', self.gf('django.db.models.fields.CharField')(default=None, max_length=50)),
            ('payment_id', self.gf('django.db.models.fields.CharField')(max_length=64)),
            ('transaction_id', self.gf('django.db.models.fields.CharField')(max_length=64, null=True, blank=True)),
            ('status', self.gf('django.db.models.fields.SmallIntegerField')(max_length=2)),
            ('referrer', self.gf('django.db.models.fields.TextField')(blank=True)),
        ))
        db.send_create_signal('donate', ['Donation'])

    def backwards(self, orm):
        # Deleting model 'Donation'
        db.delete_table('donate_donation')

    models = {
        'donate.donation': {
            'Meta': {'object_name': 'Donation'},
            'amount': ('django.db.models.fields.DecimalField', [], {'default': 'None', 'max_digits': '10', 'decimal_places': '2'}),
            'clearing_date': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'date_created': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'db_index': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'payment_id': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'payment_provider': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '50'}),
            'referrer': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'send_annual_reminder': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'status': ('django.db.models.fields.SmallIntegerField', [], {'max_length': '2'}),
            'transaction_id': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'})
        }
    }

    complete_apps = ['donate']