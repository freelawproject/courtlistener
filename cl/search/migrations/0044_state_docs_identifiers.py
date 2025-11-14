# Generated Django migration
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('search', '0043_add_date_fields_citation_model')]

    operations = [
        migrations.CreateModel(
            name='StateCourtDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_number', models.CharField(
                    max_length=32, blank=True, db_index=True,
                    help_text="If the file is a document, the number is the document_number in RECAP docket."
                )),
                ('document_type', models.IntegerField(
                    help_text="Whether this is a regular document or an attachment.",
                    choices=[(1, "PACER Document"), (2, "Attachment")],  # Replace with your actual DOCUMENT_TYPES
                )),
                ('description', models.TextField(
                    blank=True,
                    help_text="The short description of the docket entry that appears on the attachments page."
                )),
                ('source', models.CharField(
                    max_length=64, default='acis', db_index=True,
                    help_text="Source system name, e.g., 'acis', 'findlaw'"
                )),
                ('source_url', models.TextField(
                    blank=True, null=True, help_text="Original public URL to the document"
                )),
                ('is_available', models.BooleanField(
                    default=False, blank=True, null=True,
                    help_text="True if the item is available in RECAP"
                )),
                ('is_sealed', models.BooleanField(
                    null=True, help_text="Is this item sealed or otherwise unavailable on PACER?"
                )),
                ('docket_entry', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='state_court_documents',
                    to='dockets.docketentry',
                    help_text="Foreign Key to the DocketEntry object to which it belongs. Multiple documents can belong to a DocketEntry. (Attachments and Documents together)"
                )),
                ('tags', models.ManyToManyField(
                    to='search.Tag', blank=True, related_name='recap_documents',
                    help_text="The tags associated with the document."
                )),
            ],
            options={
                'ordering': ('document_type', 'document_number', 'source_url'),
                'unique_together': {('docket_entry', 'document_number', 'source_url')},
            },
        ),
        migrations.AddIndex(
            model_name='statecourtdocument',
            index=models.Index(
                fields=['document_type', 'document_number', 'source_url'],
                name='search_statecourtdocument_document_type_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='statecourtdocument',
            index=models.Index(
                fields=['filepath_local'],
                name='search_recapdocument_filepath_local_7dc6b0e53ccf753_uniq'
            ),
        ),
        migrations.AddIndex(
            model_name='statecourtdocument',
            index=models.Index(
                fields=['source', 'source_url'],
                name='search_statecourtdocument_source_url_idx'
            ),
        ),

        migrations.CreateModel(
            name='OpinionsCitedByStateCourtDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('depth', models.IntegerField(
                    default=1,
                    help_text="The number of times the cited opinion was cited in the citing document"
                )),
                ('citing_document', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cited_opinions',
                    to='search.statecourtdocument'
                )),
                ('cited_opinion', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='citing_documents',
                    to='opinions.opinion'
                )),
            ],
            options={
                'verbose_name_plural': 'Opinions cited by State Court document',
            },
        ),
        migrations.AddConstraint(
            model_name='opinionscitedbystatecourtdocument',
            constraint=models.UniqueConstraint(
                fields=['citing_document', 'cited_opinion'],
                name='unique_citing_cited_pair'
            ),
        ),
        migrations.AddIndex(
            model_name='opinionscitedbystatecourtdocument',
            index=models.Index(fields=['depth'], name='opinionscited_depth_idx')
        ),

        migrations.CreateModel(
            name='CaseIdentifier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('id_type', models.CharField(max_length=64, db_index=True,
                                             help_text="Type of identifier (e.g., 'S', 'LA', 'Crim', 'CalReporter')")),
                ('identifier', models.CharField(max_length=128, db_index=True)),
                ('note', models.CharField(max_length=255, null=True, blank=True)),
                ('first_seen', models.DateTimeField(auto_now_add=True)),
                ('docket', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='identifiers',
                    to='dockets.docket',
                )),
            ],
            options={
                'unique_together': {('id_type', 'identifier')},
            },
        ),
        migrations.AddIndex(
            model_name='caseidentifier',
            index=models.Index(fields=['id_type', 'identifier'], name='search_caseidentifier_idtype_idx'),
        ),
    ]
