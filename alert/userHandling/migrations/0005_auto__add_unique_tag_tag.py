# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Adding unique constraint on 'Tag', fields ['tag']
        db.create_unique('Tag', ['tag'])

    def backwards(self, orm):
        
        # Removing unique constraint on 'Tag', fields ['tag']
        db.delete_unique('Tag', ['tag'])

    models = {
        'alertSystem.citation': {
            'Meta': {'ordering': "['caseNameFull']", 'object_name': 'Citation', 'db_table': "'Citation'"},
            'caseNameFull': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'caseNameShort': ('django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'caseNumber': ('django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '50', 'blank': 'True'}),
            'citationUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'officialCitationLexis': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'officialCitationWest': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True', 'db_index': 'False'})
        },
        'alertSystem.court': {
            'Meta': {'ordering': "['courtUUID']", 'object_name': 'Court', 'db_table': "'Court'"},
            'courtShortName': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'courtURL': ('django.db.models.fields.URLField', [], {'max_length': '200'}),
            'courtUUID': ('django.db.models.fields.CharField', [], {'max_length': '100', 'primary_key': 'True'})
        },
        'alertSystem.document': {
            'Meta': {'ordering': "['-time_retrieved']", 'object_name': 'Document', 'db_table': "'Document'"},
            'citation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.Citation']", 'null': 'True', 'blank': 'True'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.Court']"}),
            'dateFiled': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'documentHTML': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentPlainText': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'documentSHA1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'documentType': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'documentUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'download_URL': ('django.db.models.fields.URLField', [], {'max_length': '200'}),
            'excerptSummary': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.ExcerptSummary']", 'null': 'True', 'blank': 'True'}),
            'judge': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['alertSystem.Judge']", 'null': 'True', 'blank': 'True'}),
            'local_path': ('django.db.models.fields.files.FileField', [], {'max_length': '100', 'blank': 'True'}),
            'party': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['alertSystem.Party']", 'null': 'True', 'blank': 'True'}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '3', 'blank': 'True'}),
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'})
        },
        'alertSystem.excerptsummary': {
            'Meta': {'object_name': 'ExcerptSummary', 'db_table': "'ExcerptSummary'"},
            'autoExcerpt': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'courtSummary': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'excerptUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'})
        },
        'alertSystem.judge': {
            'Meta': {'ordering': "['court', 'canonicalName']", 'object_name': 'Judge', 'db_table': "'Judge'"},
            'canonicalName': ('django.db.models.fields.CharField', [], {'max_length': '150'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.Court']"}),
            'endDate': ('django.db.models.fields.DateField', [], {}),
            'judgeAvatar': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'blank': 'True'}),
            'judgeUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'startDate': ('django.db.models.fields.DateField', [], {})
        },
        'alertSystem.party': {
            'Meta': {'ordering': "['partyExtracted']", 'object_name': 'Party', 'db_table': "'Party'"},
            'partyExtracted': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'partyUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'})
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
            'doc_id': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['alertSystem.Document']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'notes': ('django.db.models.fields.CharField', [], {'max_length': '500'}),
            'tags': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['userHandling.Tag']", 'null': 'True', 'blank': 'True'})
        },
        'userHandling.tag': {
            'Meta': {'object_name': 'Tag', 'db_table': "'Tag'"},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'tag': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
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
