# -*- coding: utf-8 -*-


from django.db import migrations, models
import cl.lib.storage


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0030_auto_20170714_0700'),
    ]

    operations = [
        migrations.CreateModel(
            name='FinancialDisclosure',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('year', models.SmallIntegerField(help_text='The year that the disclosure corresponds with', db_index=True)),
                ('filepath', models.FileField(help_text='The disclosure report itself', storage=cl.lib.storage.IncrementingFileSystemStorage(), upload_to='financial-disclosures/', db_index=True)),
                ('thumbnail', models.FileField(help_text='A thumbnail of the first page of the disclosure form', storage=cl.lib.storage.IncrementingFileSystemStorage(), null=True, upload_to='financial-disclosures/thumbnails/', blank=True)),
                ('thumbnail_status', models.SmallIntegerField(default=0, help_text='The status of the thumbnail generation', choices=[(0, 'Thumbnail needed'), (1, 'Thumbnail completed successfully'), (2, 'Unable to generate thumbnail')])),
                ('page_count', models.SmallIntegerField(help_text='The number of pages in the disclosure report')),
                ('person', models.ForeignKey(related_name='financial_disclosures', to='people_db.Person', help_text='The person that the document is associated with.',
                                             on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('-year',),
            },
        ),
    ]
