# -*- coding: utf-8 -*-
from south.v2 import DataMigration


class Migration(DataMigration):
    def forwards(self, orm):
        # Note: Remember to use orm['appname.ModelName'] rather than "from appname.models..."
        for doc in orm.Document.objects.all().iterator():
            print "Working on document: %s" % doc.pk
            docket = orm.Docket.objects.create(
                court=doc.court,
                case_name=doc.citation.case_name,
                slug=doc.citation.slug,
                blocked=doc.blocked,
                date_blocked=doc.date_blocked,
            )
            docket.save()
            doc.docket = docket
            doc.save()

    def backwards(self, orm):
        for doc in orm.Document.objects.all().iterator():
            docket = doc.docket
            docket.delete()
            doc.docket = None
            doc.save()

    models = {
        u'search.citation': {
            'Meta': {'object_name': 'Citation', 'db_table': "'Citation'"},
            'case_name': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'docket_number': (
                'django.db.models.fields.CharField', [], {'max_length': '5000', 'null': 'True', 'blank': 'True'}),
            'federal_cite_one': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'federal_cite_three': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'federal_cite_two': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lexis_cite': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'neutral_cite': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'scotus_early_cite': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True'}),
            'specialty_cite_one': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'state_cite_one': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'state_cite_regional': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'state_cite_three': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'state_cite_two': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'}),
            'westlaw_cite': (
                'django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'blank': 'True'})
        },
        u'search.court': {
            'Meta': {'ordering': "['position']", 'object_name': 'Court', 'db_table': "'Court'"},
            'citation_string': ('django.db.models.fields.CharField', [], {'max_length': '100', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [],
                              {'auto_now': 'True', 'null': 'True', 'db_index': 'True', 'blank': 'True'}),
            'end_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'full_name': ('django.db.models.fields.CharField', [], {'max_length': "'200'"}),
            'has_opinion_scraper': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'has_oral_argument_scraper': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'id': ('django.db.models.fields.CharField', [], {'max_length': '15', 'primary_key': 'True'}),
            'in_use': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'jurisdiction': ('django.db.models.fields.CharField', [], {'max_length': '3'}),
            'notes': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'position': (
                'django.db.models.fields.FloatField', [], {'unique': 'True', 'null': 'True', 'db_index': 'True'}),
            'short_name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'start_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'url': ('django.db.models.fields.URLField', [], {'max_length': '500'})
        },
        u'search.docket': {
            'Meta': {'object_name': 'Docket'},
            'blocked': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'case_name': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'court': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['search.Court']", 'null': 'True'}),
            'date_blocked': (
                'django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [],
                              {'auto_now': 'True', 'null': 'True', 'db_index': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50', 'null': 'True'})
        },
        u'search.document': {
            'Meta': {'object_name': 'Document', 'db_table': "'Document'"},
            'blocked': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'cases_cited': ('django.db.models.fields.related.ManyToManyField', [],
                            {'blank': 'True', 'related_name': "'citing_opinions'", 'null': 'True',
                             'symmetrical': 'False', 'to': u"orm['search.Citation']"}),
            'citation': ('django.db.models.fields.related.ForeignKey', [],
                         {'blank': 'True', 'related_name': "'parent_documents'", 'null': 'True',
                          'to': u"orm['search.Citation']"}),
            'citation_count': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            'date_blocked': (
                'django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_filed': (
                'django.db.models.fields.DateField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'date_modified': ('django.db.models.fields.DateTimeField', [],
                              {'auto_now': 'True', 'null': 'True', 'db_index': 'True', 'blank': 'True'}),
            'docket': ('django.db.models.fields.related.ForeignKey', [],
                       {'blank': 'True', 'related_name': "'documents'", 'null': 'True', 'to': u"orm['search.Docket']"}),
            'download_url': ('django.db.models.fields.URLField', [],
                             {'db_index': 'True', 'max_length': '500', 'null': 'True', 'blank': 'True'}),
            'extracted_by_ocr': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'html': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'html_lawbox': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'html_with_citations': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_stub_document': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'judges': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'local_path': (
                'django.db.models.fields.files.FileField', [],
                {'db_index': 'True', 'max_length': '100', 'blank': 'True'}),
            'nature_of_suit': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'plain_text': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'precedential_status': (
                'django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '50', 'blank': 'True'}),
            'sha1': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '3', 'blank': 'True'}),
            'time_retrieved': (
                'django.db.models.fields.DateTimeField', [],
                {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'})
        }
    }

    complete_apps = ['search']
    symmetrical = True
