# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Adding model 'Favorite'
        db.create_table('Favorite', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('notes', self.gf('django.db.models.fields.CharField')(max_length=500)),
        ))
        db.send_create_signal('userHandling', ['Favorite'])

        # Adding M2M table for field tags on 'Favorite'
        db.create_table('Favorite_tags', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('favorite', models.ForeignKey(orm['userHandling.favorite'], null=False)),
            ('tag', models.ForeignKey(orm['userHandling.tag'], null=False))
        ))
        db.create_unique('Favorite_tags', ['favorite_id', 'tag_id'])

        # Adding model 'Tag'
        db.create_table('Tag', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('tag', self.gf('django.db.models.fields.CharField')(max_length=30)),
        ))
        db.send_create_signal('userHandling', ['Tag'])

        # Adding M2M table for field favorite on 'UserProfile'
        db.create_table('UserProfile_favorite', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('userprofile', models.ForeignKey(orm['userHandling.userprofile'], null=False)),
            ('favorite', models.ForeignKey(orm['userHandling.favorite'], null=False))
        ))
        db.create_unique('UserProfile_favorite', ['userprofile_id', 'favorite_id'])

    def backwards(self, orm):
        
        # Deleting model 'Favorite'
        db.delete_table('Favorite')

        # Removing M2M table for field tags on 'Favorite'
        db.delete_table('Favorite_tags')

        # Deleting model 'Tag'
        db.delete_table('Tag')

        # Removing M2M table for field favorite on 'UserProfile'
        db.delete_table('UserProfile_favorite')

    models = {
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
        'userHandling.alert': {
            'Meta': {'ordering': "['alertFrequency', 'alertText']", 'object_name': 'Alert', 'db_table': "'Alert'"},
            'alertFrequency': ('django.db.models.fields.CharField', [], {'max_length': '10'}),
            'alertName': ('django.db.models.fields.CharField', [], {'max_length': '75'}),
            'alertPrivacy': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'alertText': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'alertUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lastHitDate': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'sendNegativeAlert': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        },
        'userHandling.barmembership': {
            'Meta': {'ordering': "['barMembership']", 'object_name': 'BarMembership', 'db_table': "'BarMembership'"},
            'barMembership': ('django.contrib.localflavor.us.models.USStateField', [], {'max_length': '2'}),
            'barMembershipUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'})
        },
        'userHandling.favorite': {
            'Meta': {'object_name': 'Favorite', 'db_table': "'Favorite'"},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'notes': ('django.db.models.fields.CharField', [], {'max_length': '500'}),
            'tags': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['userHandling.Tag']", 'null': 'True', 'blank': 'True'})
        },
        'userHandling.tag': {
            'Meta': {'object_name': 'Tag', 'db_table': "'Tag'"},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'tag': ('django.db.models.fields.CharField', [], {'max_length': '30'})
        },
        'userHandling.userprofile': {
            'Meta': {'object_name': 'UserProfile', 'db_table': "'UserProfile'"},
            'activationKey': ('django.db.models.fields.CharField', [], {'max_length': '40'}),
            'alert': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['userHandling.Alert']", 'null': 'True', 'blank': 'True'}),
            'avatar': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'blank': 'True'}),
            'barmembership': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['userHandling.BarMembership']", 'null': 'True', 'blank': 'True'}),
            'emailConfirmed': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'employer': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'favorite': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['userHandling.Favorite']", 'null': 'True', 'blank': 'True'}),
            'key_expires': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'location': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'plaintextPreferred': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['auth.User']", 'unique': 'True'}),
            'userProfileUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'wantsNewsletter': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        }
    }

    complete_apps = ['userHandling']
