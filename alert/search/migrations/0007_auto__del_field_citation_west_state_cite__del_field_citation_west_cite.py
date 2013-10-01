# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        db.rename_column('Citation', 'west_cite', 'federal_cite_one')
        db.rename_column('Citation', 'west_state_cite', 'state_cite_one')

        # Adding field 'Citation.federal_cite_two'
        db.add_column('Citation', 'federal_cite_two',
                      self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True),
                      keep_default=False)

        # Adding field 'Citation.federal_cite_three'
        db.add_column('Citation', 'federal_cite_three',
                      self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True),
                      keep_default=False)

        # Adding field 'Citation.state_cite_two'
        db.add_column('Citation', 'state_cite_two',
                      self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True),
                      keep_default=False)

        # Adding field 'Citation.state_cite_three'
        db.add_column('Citation', 'state_cite_three',
                      self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True),
                      keep_default=False)

        # Adding field 'Citation.state_cite_regional'
        db.add_column('Citation', 'state_cite_regional',
                      self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True),
                      keep_default=False)

        # Adding field 'Citation.specialty_cite_one'
        db.add_column('Citation', 'specialty_cite_one',
                      self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True),
                      keep_default=False)

        # Adding field 'Citation.scotus_early_cite'
        db.add_column('Citation', 'scotus_early_cite',
                      self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True),
                      keep_default=False)

        # Adding field 'Citation.westlaw_cite'
        db.add_column('Citation', 'westlaw_cite',
                      self.gf('django.db.models.fields.CharField')(max_length=50, null=True, blank=True),
                      keep_default=False)

    def backwards(self, orm):
        db.rename_column('Citation', 'federal_cite_one', 'west_cite')
        db.rename_column('Citation', 'state_cite_one', 'west_state_cite')

        # Deleting field 'Citation.federal_cite_two'
        db.delete_column('Citation', 'federal_cite_two')

        # Deleting field 'Citation.federal_cite_three'
        db.delete_column('Citation', 'federal_cite_three')

        # Deleting field 'Citation.state_cite_two'
        db.delete_column('Citation', 'state_cite_two')

        # Deleting field 'Citation.state_cite_three'
        db.delete_column('Citation', 'state_cite_three')

        # Deleting field 'Citation.state_cite_regional'
        db.delete_column('Citation', 'state_cite_regional')

        # Deleting field 'Citation.specialty_cite_one'
        db.delete_column('Citation', 'specialty_cite_one')

        # Deleting field 'Citation.scotus_early_cite'
        db.delete_column('Citation', 'scotus_early_cite')

        # Deleting field 'Citation.westlaw_cite'
        db.delete_column('Citation', 'westlaw_cite')

    models = {
        'search.citation': {
            'Meta': {'object_name': 'Citation', 'db_table': "'Citation'"},
            'case_name': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'citationUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'docket_number': ('django.db.models.fields.CharField', [], {'max_length': '100', 'null': 'True', 'blank': 'True'}),
            'federal_cite_one': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'federal_cite_three': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'federal_cite_two': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
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
        'search.court': {
            'Meta': {'ordering': "['position']", 'object_name': 'Court', 'db_table': "'Court'"},
            'URL': ('django.db.models.fields.URLField', [], {'max_length': '200'}),
            'citation_string': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'courtUUID': ('django.db.models.fields.CharField', [], {'max_length': '15', 'primary_key': 'True'}),
            'end_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'full_name': ('django.db.models.fields.CharField', [], {'max_length': "'200'"}),
            'in_use': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'jurisdiction': ('django.db.models.fields.CharField', [], {'max_length': '3'}),
            'notes': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
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
            'date_blocked': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'date_filed': ('django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'documentUUID': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'download_URL': ('django.db.models.fields.URLField', [], {'max_length': '200', 'db_index': 'True'}),
            'extracted_by_ocr': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'html': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'html_with_citations': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'judges': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'local_path': ('django.db.models.fields.files.FileField', [], {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'nature_of_suit': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'plain_text': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'precedential_status': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'sha1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '3', 'blank': 'True'}),
            'time_retrieved': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'})
        }
    }

    complete_apps = ['search']
