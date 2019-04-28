# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0042_make_pacer_doc_id_nullable'),
        ('favorites', '0003_auto_20160331_1116'),
    ]

    operations = [
        migrations.AddField(
            model_name='favorite',
            name='docket_id',
            field=models.ForeignKey(verbose_name=b'the docket that is favorited', blank=True, to='search.Docket', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='favorite',
            name='recap_doc_id',
            field=models.ForeignKey(verbose_name=b'the RECAP document that is favorited', blank=True, to='search.RECAPDocument', null=True,
                                    on_delete=models.CASCADE),
        ),
        migrations.AlterUniqueTogether(
            name='favorite',
            unique_together=set([('cluster_id', 'user'), ('audio_id', 'user'), ('recap_doc_id', 'user'), ('docket_id', 'user')]),
        ),
    ]
