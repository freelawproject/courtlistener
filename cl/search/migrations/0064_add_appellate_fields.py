# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people_db', '0039_add_role_raw'),
        ('search', '0063_add_pacer_rss_field'),
    ]

    operations = [
        migrations.CreateModel(
            name='OriginatingCourtInformation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_created', models.DateTimeField(help_text=b'The time when this item was created', auto_now_add=True, db_index=True)),
                ('date_modified', models.DateTimeField(help_text=b'The last moment when the item was modified.', auto_now=True, db_index=True)),
                ('assigned_to_str', models.TextField(help_text=b'The judge that the case was assigned to, as a string.', blank=True)),
                ('court_reporter', models.TextField(help_text=b'The court reporter responsible for the case.', blank=True)),
                ('date_disposed', models.DateField(help_text=b'The date the case was disposed at the lower court.', null=True, blank=True)),
                ('date_filed', models.DateField(help_text=b'The date the case was filed in the lower court.', null=True, blank=True)),
                ('date_judgement', models.DateField(help_text=b'The date of the order or judgement in the lower court.', null=True, blank=True)),
                ('date_judgement_oed', models.DateField(help_text=b'The date the judgement was entered on the docket at the lower court.', null=True, blank=True)),
                ('date_filed_noa', models.DateField(help_text=b'The date the notice of appeal was filed for the case.', null=True, blank=True)),
                ('date_received_coa', models.DateField(help_text=b'The date the case was received at the court of appeals.', null=True, blank=True)),
                ('assigned_to', models.ForeignKey(related_name='original_court_info', blank=True, to='people_db.Person', help_text=b'The judge the case was assigned to.', null=True,
                                                  on_delete=models.CASCADE)),
            ],
        ),
        migrations.AddField(
            model_name='docket',
            name='appeal_from',
            field=models.ForeignKey(related_name='+', blank=True, to='search.Court', help_text=b'In appellate cases, this is the lower court or administrative body where this case was originally heard. This field is frequently blank due to it not being populated historically or due to our inability to normalize the value in appeal_from_str.', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='docket',
            name='appeal_from_str',
            field=models.TextField(help_text=b'In appeallate cases, this is the lower court or administrative body where this case was originally heard. This field is frequently blank due to it not being populated historically. This field may have values when the appeal_from field does not. That can happen if we are unable to normalize the value in this field.', blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='appellate_case_type_information',
            field=models.TextField(help_text=b"Information about a case from the appellate docket in PACER. For example, 'civil, private, bankruptcy'.", blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='appellate_fee_status',
            field=models.TextField(help_text=b'The status of the fee in the appellate court. Can be used as a hint as to whether the government is the appellant (in which case the fee is waived).', blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='panel',
            field=models.ManyToManyField(help_text=b'The empaneled judges for the case. Currently an unused field but planned to be used in conjunction with the panel_str field.', related_name='empanelled_dockets', to='people_db.Person', blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='panel_str',
            field=models.TextField(help_text=b"The initials of the judges on the panel that heard this case. This field is similar to the 'judges' field on the cluster, but contains initials instead of full judge names, and applies to the case on the whole instead of only to a specific decision.", blank=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='judges',
            field=models.TextField(help_text=b'The judges that participated in the opinion as a simple text string. This field is used when normalized judges cannot be placed into the panel field.', blank=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='panel',
            field=models.ManyToManyField(help_text=b'The judges that participated in the opinion', related_name='opinion_clusters_participating_judges', to='people_db.Person', blank=True),
        ),
        migrations.AddField(
            model_name='docket',
            name='originating_court',
            field=models.OneToOneField(related_name='docket', null=True, blank=True, to='search.OriginatingCourtInformation', help_text=b'Lower court information for appellate dockets',
                                       on_delete=models.CASCADE),
        ),
    ]
