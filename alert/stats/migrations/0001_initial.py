# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Stat'
        db.create_table('stats_stat', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=50, db_index=True)),
            ('date_logged', self.gf('django.db.models.fields.DateField')(db_index=True)),
            ('count', self.gf('django.db.models.fields.IntegerField')()),
        ))
        db.send_create_signal('stats', ['Stat'])

        # Adding unique constraint on 'Stat', fields ['date_logged', 'name']
        db.create_unique('stats_stat', ['date_logged', 'name'])


    def backwards(self, orm):
        # Removing unique constraint on 'Stat', fields ['date_logged', 'name']
        db.delete_unique('stats_stat', ['date_logged', 'name'])

        # Deleting model 'Stat'
        db.delete_table('stats_stat')


    models = {
        'stats.stat': {
            'Meta': {'unique_together': "(('date_logged', 'name'),)", 'object_name': 'Stat'},
            'count': ('django.db.models.fields.IntegerField', [], {}),
            'date_logged': ('django.db.models.fields.DateField', [], {'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50', 'db_index': 'True'})
        }
    }

    complete_apps = ['stats']