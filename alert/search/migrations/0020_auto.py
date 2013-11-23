# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding index on 'Document', fields ['date_blocked']
        db.create_index('Document', ['date_blocked'])

        # Adding index on 'Document', fields ['precedential_status']
        db.create_index('Document', ['precedential_status'])

        # Adding index on 'Document', fields ['extracted_by_ocr']
        db.create_index('Document', ['extracted_by_ocr'])

        # Adding index on 'Document', fields ['citation_count']
        db.create_index('Document', ['citation_count'])


    def backwards(self, orm):
        # Removing index on 'Document', fields ['citation_count']
        db.delete_index('Document', ['citation_count'])

        # Removing index on 'Document', fields ['extracted_by_ocr']
        db.delete_index('Document', ['extracted_by_ocr'])

        # Removing index on 'Document', fields ['precedential_status']
        db.delete_index('Document', ['precedential_status'])

        # Removing index on 'Document', fields ['date_blocked']
        db.delete_index('Document', ['date_blocked'])


    models = {
        u'search.citation': {
            'Meta': {'object_name': 'Citation', 'db_table': "'Citation'"},
            'case_name': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'docket_number': ('django.db.models.fields.CharField', [], {'max_length': '5000', 'null': 'True', 'blank': 'True'}),
            'federal_cite_one': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'federal_cite_three': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'federal_cite_two': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lexis_cite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'neutral_cite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'scotus_early_cite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True'}),
            'specialty_cite_one': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'state_cite_one': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'state_cite_regional': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'state_cite_three': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'state_cite_two': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'westlaw_cite': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'})
        },
        u'search.court': {
            'Meta': {'ordering': "['position']", 'object_name': 'Court', 'db_table': "'Court'"},
            'URL': ('django.db.models.fields.URLField', [], {'max_length': '500'}),
            'citation_string': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'null': 'True', 'db_index': 'True', 'blank': 'True'}),
            'end_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'full_name': ('django.db.models.fields.CharField', [], {'max_length': "'200'"}),
            'id': ('django.db.models.fields.CharField', [], {'max_length': '15', 'primary_key': 'True'}),
            'in_use': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'jurisdiction': ('django.db.models.fields.CharField', [], {'max_length': '3'}),
            'notes': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'position': ('django.db.models.fields.FloatField', [], {'unique': 'True', 'null': 'True', 'db_index': 'True'}),
            'short_name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'start_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'})
        },
        u'search.document': {
            'Meta': {'object_name': 'Document', 'db_table': "'Document'"},
            'blocked': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'cases_cited': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'citing_cases'", 'null': 'True', 'symmetrical': 'False', 'to': u"orm['search.Citation']"}),
            'citation': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['search.Citation']", 'null': 'True', 'blank': 'True'}),
            'citation_count': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['search.Court']", 'null': 'True'}),
            'date_blocked': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_filed': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'null': 'True', 'db_index': 'True', 'blank': 'True'}),
            'download_URL': ('django.db.models.fields.URLField', [], {'max_length': '500', 'db_index': 'True'}),
            'extracted_by_ocr': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'html': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'html_lawbox': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'html_with_citations': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_stub_document': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'judges': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'local_path': ('django.db.models.fields.files.FileField', [], {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'nature_of_suit': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'pagerank': ('django.db.models.fields.FloatField', [], {'default': '0', 'db_index': 'True'}),
            'plain_text': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'precedential_status': ('django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '50', 'blank': 'True'}),
            'sha1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '3', 'blank': 'True'}),
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'})
        }
    }

    complete_apps = ['search']