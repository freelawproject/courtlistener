# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'BarMembership'
        db.create_table('BarMembership', (
            ('barMembershipUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('barMembership', self.gf('django.contrib.localflavor.us.models.USStateField')(max_length=2)),
        ))
        db.send_create_signal('userHandling', ['BarMembership'])

        # Adding model 'UserProfile'
        db.create_table('UserProfile', (
            ('userProfileUUID', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('user', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['auth.User'], unique=True)),
            ('location', self.gf('django.db.models.fields.CharField')(max_length=100, blank=True)),
            ('employer', self.gf('django.db.models.fields.CharField')(max_length=100, blank=True)),
            ('avatar', self.gf('django.db.models.fields.files.ImageField')(max_length=100, blank=True)),
            ('wantsNewsletter', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('plaintextPreferred', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('activationKey', self.gf('django.db.models.fields.CharField')(max_length=40)),
            ('key_expires', self.gf('django.db.models.fields.DateTimeField')(null=True, blank=True)),
            ('emailConfirmed', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal('userHandling', ['UserProfile'])

        # Adding M2M table for field barmembership on 'UserProfile'
        db.create_table('UserProfile_barmembership', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('userprofile', models.ForeignKey(orm['userHandling.userprofile'], null=False)),
            ('barmembership', models.ForeignKey(orm['userHandling.barmembership'], null=False))
        ))
        db.create_unique('UserProfile_barmembership', ['userprofile_id', 'barmembership_id'])

        # Adding M2M table for field alert on 'UserProfile'
        db.create_table('UserProfile_alert', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('userprofile', models.ForeignKey(orm['userHandling.userprofile'], null=False)),
            ('alert', models.ForeignKey(orm['alerts.alert'], null=False))
        ))
        db.create_unique('UserProfile_alert', ['userprofile_id', 'alert_id'])

        # Adding M2M table for field favorite on 'UserProfile'
        db.create_table('UserProfile_favorite', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('userprofile', models.ForeignKey(orm['userHandling.userprofile'], null=False)),
            ('favorite', models.ForeignKey(orm['favorites.favorite'], null=False))
        ))
        db.create_unique('UserProfile_favorite', ['userprofile_id', 'favorite_id'])

    def backwards(self, orm):
        # Deleting model 'BarMembership'
        db.delete_table('BarMembership')

        # Deleting model 'UserProfile'
        db.delete_table('UserProfile')

        # Removing M2M table for field barmembership on 'UserProfile'
        db.delete_table('UserProfile_barmembership')

        # Removing M2M table for field alert on 'UserProfile'
        db.delete_table('UserProfile_alert')

        # Removing M2M table for field favorite on 'UserProfile'
        db.delete_table('UserProfile_favorite')

    models = {
        'alerts.alert': {
            'Meta': {'ordering': "['alertFrequency', 'alertText']", 'object_name': 'Alert', 'db_table': "'Alert'"},
            'alertFrequency': ('django.db.models.fields.CharField', [], {'max_length': '10'}),
            'alertName': ('django.db.models.fields.CharField', [], {'max_length': '75'}),
            'alertText': ('django.db.models.fields.CharField', [], {'max_length': '2500'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lastHitDate': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'sendNegativeAlert': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        },
        'auth.group': {
            'Meta': {'object_name': 'Group'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        'auth.permission': {
            'Meta': {'ordering': "('content_type__app_label', 'content_type__model', 'codename')", 'unique_together': "(('content_type', 'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'favorites.favorite': {
            'Meta': {'object_name': 'Favorite', 'db_table': "'Favorite'"},
            'doc_id': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['search.Document']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'notes': ('django.db.models.fields.TextField', [], {'max_length': '500', 'blank': 'True'})
        },
        'search.citation': {
            'Meta': {'object_name': 'Citation', 'db_table': "'Citation'"},
            'case_name': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'citationUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'docketNumber': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'lexisCite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'neutral_cite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True'}),
            'westCite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'})
        },
        'search.court': {
            'Meta': {'ordering': "['position']", 'object_name': 'Court', 'db_table': "'Court'"},
            'URL': ('django.db.models.fields.URLField', [], {'max_length': '200'}),
            'citation_string': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'courtUUID': ('django.db.models.fields.CharField', [], {'max_length': '6', 'primary_key': 'True'}),
            'end_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'full_name': ('django.db.models.fields.CharField', [], {'max_length': "'200'"}),
            'in_use': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'jurisdiction': ('django.db.models.fields.CharField', [], {'max_length': '3'}),
            'position': ('django.db.models.fields.FloatField', [], {'unique': 'True', 'null': 'True', 'db_index': 'True'}),
            'short_name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'start_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'})
        },
        'search.document': {
            'Meta': {'object_name': 'Document', 'db_table': "'Document'"},
            'blocked': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'cases_cited': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'citing_cases'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['search.Citation']"}),
            'citation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['search.Citation']", 'null': 'True', 'blank': 'True'}),
            'citation_count': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['search.Court']"}),
            'dateFiled': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_blocked': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'documentHTML': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentPlainText': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentSHA1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'documentType': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'documentUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'download_URL': ('django.db.models.fields.URLField', [], {'max_length': '200', 'db_index': 'True'}),
            'extracted_by_ocr': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'html_with_citations': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'local_path': ('django.db.models.fields.files.FileField', [], {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '3', 'blank': 'True'}),
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'})
        },
        'userHandling.barmembership': {
            'Meta': {'ordering': "['barMembership']", 'object_name': 'BarMembership', 'db_table': "'BarMembership'"},
            'barMembership': ('django.contrib.localflavor.us.models.USStateField', [], {'max_length': '2'}),
            'barMembershipUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'})
        },
        'userHandling.userprofile': {
            'Meta': {'object_name': 'UserProfile', 'db_table': "'UserProfile'"},
            'activationKey': ('django.db.models.fields.CharField', [], {'max_length': '40'}),
            'alert': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['alerts.Alert']", 'null': 'True', 'blank': 'True'}),
            'avatar': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'blank': 'True'}),
            'barmembership': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['userHandling.BarMembership']", 'null': 'True', 'blank': 'True'}),
            'emailConfirmed': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'employer': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'favorite': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'users'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['favorites.Favorite']"}),
            'key_expires': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'location': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'plaintextPreferred': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['auth.User']", 'unique': 'True'}),
            'userProfileUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'wantsNewsletter': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        }
    }

    complete_apps = ['userHandling']
