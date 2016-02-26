# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0011_auto_20151222_1240'),
        ('people_db', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='opinion',
            name='author',
            field=models.ForeignKey(related_name='opinions_written', blank=True, to='people_db.Person', help_text=b'The primary author of this opinion', null=True),
        ),
        migrations.AlterField(
            model_name='opinion',
            name='joined_by',
            field=models.ManyToManyField(help_text=b'Other judges that joined the primary author in this opinion', related_name='opinions_joined', to='people_db.Person', blank=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='non_participating_judges',
            field=models.ManyToManyField(help_text=b'The judges that heard the case, but did not participate in the opinion', related_name='opinion_clusters_non_participating_judges', to='people_db.Person', blank=True),
        ),
        migrations.AlterField(
            model_name='opinioncluster',
            name='panel',
            field=models.ManyToManyField(help_text=b'The judges that heard the oral arguments', related_name='opinion_clusters_participating_judges', to='people_db.Person', blank=True),
        ),
    ]
