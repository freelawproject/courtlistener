# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def remove_duplicate_citation_objects(apps, schema_editor):
    """Remove duplicate citations"""
    OpinionsCited = apps.get_model("search", "OpinionsCited")
    last_seen = ''
    count = 0
    rows = OpinionsCited.objects.all().order_by('citing_opinion',
                                                'cited_opinion')
    for row in rows:
        row_id = '%s;%s' % (row.citing_opinion_id, row.cited_opinion_id)
        if row_id == last_seen:
            count += 1
            row.delete()
        else:
            last_seen = row_id

    print "Deleted %s citation objects." % count


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0009_auto_20151210_1124'),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_citation_objects),
        migrations.AlterUniqueTogether(
            name='opinionscited',
            unique_together=set([('citing_opinion', 'cited_opinion')]),
        ),
    ]
