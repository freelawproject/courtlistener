# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Donation'
        db.create_table('donate_donation', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('date_modified', self.gf('django.db.models.fields.DateTimeField')(auto_now=True, db_index=True, blank=True)),
            ('date_created', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, db_index=True, blank=True)),
            ('email_address', self.gf('django.db.models.fields.EmailField')(max_length=254)),
            ('frequency', self.gf('django.db.models.fields.CharField')(max_length=10)),
            ('renew_annually', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('amount', self.gf('django.db.models.fields.DecimalField')(max_digits=9, decimal_places=2)),
            ('total', self.gf('django.db.models.fields.DecimalField')(max_digits=10, decimal_places=2)),
            ('currency', self.gf('django.db.models.fields.CharField')(max_length=10)),
            ('payment_provider', self.gf('django.db.models.fields.CharField')(max_length=50)),
            ('referrer', self.gf('django.db.models.fields.TextField')()),
        ))
        db.send_create_signal('donate', ['Donation'])

    def backwards(self, orm):
        # Deleting model 'Donation'
        db.delete_table('donate_donation')

    models = {
        'donate.donation': {
            'Meta': {'object_name': 'Donation'},
            'amount': ('django.db.models.fields.DecimalField', [], {'max_digits': '9', 'decimal_places': '2'}),
            'currency': ('django.db.models.fields.CharField', [], {'max_length': '10'}),
            'date_created': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'db_index': 'True', 'blank': 'True'}),
            'email_address': ('django.db.models.fields.EmailField', [], {'max_length': '254'}),
            'frequency': ('django.db.models.fields.CharField', [], {'max_length': '10'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'payment_provider': ('django.db.models.fields.CharField', [], {'max_length': '50'}),
            'referrer': ('django.db.models.fields.TextField', [], {}),
            'renew_annually': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'total': ('django.db.models.fields.DecimalField', [], {'max_digits': '10', 'decimal_places': '2'})
        }
    }

    complete_apps = ['donate']
