# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import cl.lib.model_helpers
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Court',
            fields=[
                ('id', models.CharField(help_text=b'a unique ID for each court as used in URLs', max_length=15, serialize=False, primary_key=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified', auto_now=True, db_index=True)),
                ('in_use', models.BooleanField(default=False, help_text=b'Whether this jurisdiction is in use in CourtListener -- increasingly True')),
                ('has_opinion_scraper', models.BooleanField(default=False, help_text=b'Whether the jurisdiction has a scraper that obtains opinions automatically.')),
                ('has_oral_argument_scraper', models.BooleanField(default=False, help_text=b'Whether the jurisdiction has a scraper that obtains oral arguments automatically.')),
                ('position', models.FloatField(help_text=b'A dewey-decimal-style numeral indicating a hierarchical ordering of jurisdictions', unique=True, null=True, db_index=True)),
                ('citation_string', models.CharField(help_text=b'the citation abbreviation for the court as dictated by Blue Book', max_length=100, blank=True)),
                ('short_name', models.CharField(help_text=b'a short name of the court', max_length=100)),
                ('full_name', models.CharField(help_text=b'the full name of the court', max_length=b'200')),
                ('url', models.URLField(help_text=b'the homepage for each court or the closest thing thereto', max_length=500)),
                ('start_date', models.DateField(help_text=b'the date the court was established, if known', null=True, blank=True)),
                ('end_date', models.DateField(help_text=b'the date the court was abolished, if known', null=True, blank=True)),
                ('jurisdiction', models.CharField(help_text=b'the jurisdiction of the court, one of: F (Federal Appellate), FD (Federal District), FB (Federal Bankruptcy), FBP (Federal Bankruptcy Panel), FS (Federal Special), S (State Supreme), SA (State Appellate), ST (State Trial), SS (State Special), C (Committee), T (Testing)', max_length=3, choices=[(b'F', b'Federal Appellate'), (b'FD', b'Federal District'), (b'FB', b'Federal Bankruptcy'), (b'FBP', b'Federal Bankruptcy Panel'), (b'FS', b'Federal Special'), (b'S', b'State Supreme'), (b'SA', b'State Appellate'), (b'ST', b'State Trial'), (b'SS', b'State Special'), (b'C', b'Committee'), (b'T', b'Testing')])),
                ('notes', models.TextField(help_text=b'any notes about coverage or anything else (currently very raw)', blank=True)),
            ],
            options={
                'ordering': ['position'],
            },
        ),
        migrations.CreateModel(
            name='Docket',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', auto_now=True, db_index=True)),
                ('date_cert_granted', models.DateField(help_text=b'date cert was granted for this case, if applicable', null=True, db_index=True, blank=True)),
                ('date_cert_denied', models.DateField(help_text=b'the date cert was denied for this case, if applicable', null=True, db_index=True, blank=True)),
                ('date_argued', models.DateField(help_text=b'the date the case was argued', null=True, db_index=True, blank=True)),
                ('date_reargued', models.DateField(help_text=b'the date the case was reargued', null=True, db_index=True, blank=True)),
                ('date_reargument_denied', models.DateField(help_text=b'the date the reargument was denied', null=True, db_index=True, blank=True)),
                ('case_name_short', models.TextField(help_text=b"The abridged name of the case, often a single word, e.g. 'Marsh'", blank=True)),
                ('case_name', models.TextField(help_text=b'The standard name of the case', blank=True)),
                ('case_name_full', models.TextField(help_text=b'The full name of the case', blank=True)),
                ('slug', models.SlugField(help_text=b'URL that the document should map to (the slug)', max_length=75, null=True, db_index=False)),
                ('docket_number', models.CharField(help_text=b'The docket numbers of a case, can be consolidated and quite long', max_length=5000, null=True, blank=True)),
                ('date_blocked', models.DateField(help_text=b'The date that this opinion was blocked from indexing by search engines', null=True, db_index=True, blank=True)),
                ('blocked', models.BooleanField(default=False, help_text=b'Whether a document should be blocked from indexing by search engines', db_index=True)),
                ('court', models.ForeignKey(related_name='dockets', to='search.Court', help_text=b'The court where the docket was filed')),
            ],
        ),
        migrations.CreateModel(
            name='Opinion',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The original creation date for the item', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', auto_now=True, db_index=True)),
                ('type', models.CharField(max_length=20, choices=[(b'010combined', b'Combined Opinion'), (b'020lead', b'Lead Opinion'), (b'030concurrence', b'Concurrence'), (b'040dissent', b'Dissent')])),
                ('sha1', models.CharField(help_text=b'unique ID for the document, as generated via SHA1 of the binary file or text data', max_length=40, db_index=True)),
                ('download_url', models.URLField(help_text=b'The URL on the court website where the document was originally scraped', max_length=500, null=True, db_index=True, blank=True)),
                ('local_path', models.FileField(help_text=b'The location, relative to MEDIA_ROOT on the CourtListener server, where files are stored', upload_to=cl.lib.model_helpers.make_upload_path, storage=cl.lib.storage.IncrementingFileSystemStorage(), db_index=True, blank=True)),
                ('plain_text', models.TextField(help_text=b'Plain text of the document after extraction using pdftotext, wpd2txt, etc.', blank=True)),
                ('html', models.TextField(help_text=b'HTML of the document, if available in the original', null=True, blank=True)),
                ('html_lawbox', models.TextField(help_text=b'HTML of Lawbox documents', null=True, blank=True)),
                ('html_columbia', models.TextField(help_text=b'HTML of Columbia archive', null=True, blank=True)),
                ('html_with_citations', models.TextField(help_text=b'HTML of the document with citation links and other post-processed markup added', blank=True)),
                ('extracted_by_ocr', models.BooleanField(default=False, help_text=b'Whether OCR was used to get this document content', db_index=True)),
                ('author', models.ForeignKey(related_name='opinions_written', blank=True, to='people_db.Person', help_text=b'The primary author of this opinion', null=True)),
            ],
        ),
        migrations.CreateModel(
            name='OpinionCluster',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('judges', models.TextField(help_text=b'The judges that heard the oral arguments as a simple text string. This field is used when normalized judges cannot be placed into the panel field.', blank=True)),
                ('per_curiam', models.BooleanField(default=False, help_text=b'Was this case heard per curiam?')),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified. A value in year 1750 indicates the value is unknown', auto_now=True, db_index=True)),
                ('date_filed', models.DateField(help_text=b'The date filed by the court', db_index=True)),
                ('slug', models.SlugField(help_text=b'URL that the document should map to (the slug)', max_length=75, null=True, db_index=False)),
                ('citation_id', models.IntegerField(help_text=b'A legacy field that holds the primary key from the old citation table. Used to serve legacy APIs.', null=True, db_index=True, blank=True)),
                ('case_name_short', models.TextField(help_text=b"The abridged name of the case, often a single word, e.g. 'Marsh'", blank=True)),
                ('case_name', models.TextField(help_text=b'The shortened name of the case', blank=True)),
                ('case_name_full', models.TextField(help_text=b'The full name of the case', blank=True)),
                ('federal_cite_one', models.CharField(help_text=b'Primary federal citation', max_length=50, blank=True)),
                ('federal_cite_two', models.CharField(help_text=b'Secondary federal citation', max_length=50, blank=True)),
                ('federal_cite_three', models.CharField(help_text=b'Tertiary federal citation', max_length=50, blank=True)),
                ('state_cite_one', models.CharField(help_text=b'Primary state citation', max_length=50, blank=True)),
                ('state_cite_two', models.CharField(help_text=b'Secondary state citation', max_length=50, blank=True)),
                ('state_cite_three', models.CharField(help_text=b'Tertiary state citation', max_length=50, blank=True)),
                ('state_cite_regional', models.CharField(help_text=b'Regional citation', max_length=50, blank=True)),
                ('specialty_cite_one', models.CharField(help_text=b'Specialty citation', max_length=50, blank=True)),
                ('scotus_early_cite', models.CharField(help_text=b'Early SCOTUS citation such as How., Black, Cranch., etc.', max_length=50, blank=True)),
                ('lexis_cite', models.CharField(help_text=b'Lexis Nexus citation (e.g. 1 LEXIS 38237)', max_length=50, blank=True)),
                ('westlaw_cite', models.CharField(help_text=b'WestLaw citation (e.g. 22 WL 238)', max_length=50, blank=True)),
                ('neutral_cite', models.CharField(help_text=b'Neutral citation', max_length=50, blank=True)),
                ('scdb_id', models.CharField(help_text=b'The ID of the item in the Supreme Court Database', max_length=10, db_index=True, blank=True)),
                ('scdb_decision_direction', models.IntegerField(blank=True, help_text=b'the ideological "direction" of a decision in the Supreme Court database. More details at: http://scdb.wustl.edu/documentation.php?var=decisionDirection', null=True, choices=[(1, b'Conservative'), (2, b'Liberal'), (3, b'Unspecifiable')])),
                ('scdb_votes_majority', models.IntegerField(help_text=b'the number of justices voting in the majority in a Supreme Court decision. More details at: http://scdb.wustl.edu/documentation.php?var=majVotes', null=True, blank=True)),
                ('scdb_votes_minority', models.IntegerField(help_text=b'the number of justices voting in the minority in a Supreme Court decision. More details at: http://scdb.wustl.edu/documentation.php?var=minVotes', null=True, blank=True)),
                ('source', models.CharField(blank=True, help_text=b'the source of the cluster, one of: C (court website), R (public.resource.org), CR (court website merged with resource.org), L (lawbox), LC (lawbox merged with court), LR (lawbox merged with resource.org), LCR (lawbox merged with court and resource.org), M (manual input), A (internet archive), H (brad heath archive), Z (columbia archive), ZC (columbia merged with court), ZLC (columbia merged with lawbox and court), ZLR (columbia merged with lawbox and resource.org), ZLCR (columbia merged with lawbox, court, and resource.org), ZR (columbia merged with resource.org), ZCR (columbia merged with court and resource.org), ZL (columbia merged with lawbox)', max_length=10, choices=[(b'C', b'court website'), (b'R', b'public.resource.org'), (b'CR', b'court website merged with resource.org'), (b'L', b'lawbox'), (b'LC', b'lawbox merged with court'), (b'LR', b'lawbox merged with resource.org'), (b'LCR', b'lawbox merged with court and resource.org'), (b'M', b'manual input'), (b'A', b'internet archive'), (b'H', b'brad heath archive'), (b'Z', b'columbia archive'), (b'ZC', b'columbia merged with court'), (b'ZLC', b'columbia merged with lawbox and court'), (b'ZLR', b'columbia merged with lawbox and resource.org'), (b'ZLCR', b'columbia merged with lawbox, court, and resource.org'), (b'ZR', b'columbia merged with resource.org'), (b'ZCR', b'columbia merged with court and resource.org'), (b'ZL', b'columbia merged with lawbox')])),
                ('procedural_history', models.TextField(help_text=b'The history of the case as it jumped from court to court', blank=True)),
                ('attorneys', models.TextField(help_text=b'The attorneys that argued the case, as free text', blank=True)),
                ('nature_of_suit', models.TextField(help_text=b'The nature of the suit. For the moment can be codes or laws or whatever', blank=True)),
                ('posture', models.TextField(help_text=b'The procedural posture of the case.', blank=True)),
                ('syllabus', models.TextField(help_text=b'A summary of the issues presented in the case and the outcome.', blank=True)),
                ('citation_count', models.IntegerField(default=0, help_text=b'The number of times this document is cited by other opinion', db_index=True)),
                ('precedential_status', models.CharField(blank=True, help_text=b'The precedential status of document, one of: Published, Unpublished, Errata, Memorandum Decision, Per Curiam Opinion, Separate, Signed Opinion, In-chambers, Relating-to, Unknown', max_length=50, db_index=True, choices=[(b'Published', b'Precedential'), (b'Unpublished', b'Non-Precedential'), (b'Errata', b'Errata'), (b'Memorandum Decision', b'Memorandum Decision'), (b'Per Curiam Opinion', b'Per Curiam Opinion'), (b'Separate', b'Separate Opinion'), (b'Signed Opinion', b'Signed Opinion'), (b'In-chambers', b'In-chambers'), (b'Relating-to', b'Relating-to orders'), (b'Unknown', b'Unknown Status')])),
                ('date_blocked', models.DateField(help_text=b'The date that this opinion was blocked from indexing by search engines', null=True, db_index=True, blank=True)),
                ('blocked', models.BooleanField(default=False, help_text=b'Whether a document should be blocked from indexing by search engines', db_index=True)),
                ('docket', models.ForeignKey(related_name='clusters', to='search.Docket', help_text=b'The docket that the opinion cluster is a part of')),
                ('non_participating_judges', models.ManyToManyField(help_text=b'The judges that heard the case, but did not participate in the opinion', related_name='opinion_clusters_non_participating_judges', to='people_db.Person', blank=True)),
                ('panel', models.ManyToManyField(help_text=b'The judges that heard the oral arguments', related_name='opinion_clusters_participating_judges', to='people_db.Person', blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='OpinionsCited',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('cited_opinion', models.ForeignKey(related_name='citing_opinions', to='search.Opinion')),
                ('citing_opinion', models.ForeignKey(related_name='cited_opinions', to='search.Opinion')),
            ],
            options={
                'verbose_name_plural': 'Opinions cited',
            },
        ),
        migrations.AddField(
            model_name='opinion',
            name='cluster',
            field=models.ForeignKey(related_name='sub_opinions', to='search.OpinionCluster', help_text=b'The cluster that the opinion is a part of'),
        ),
        migrations.AddField(
            model_name='opinion',
            name='joined_by',
            field=models.ManyToManyField(help_text=b'Other judges that joined the primary author in this opinion', related_name='opinions_joined', to='people_db.Person', blank=True),
        ),
        migrations.AddField(
            model_name='opinion',
            name='opinions_cited',
            field=models.ManyToManyField(help_text=b'Opinions cited by this opinion', related_name='opinions_citing', through='search.OpinionsCited', to='search.Opinion', blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='opinionscited',
            unique_together=set([('citing_opinion', 'cited_opinion')]),
        ),
    ]
