# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0012_auto_20171122_1319'),
    ]

    operations = [
        migrations.AlterField(
            model_name='processingqueue',
            name='status',
            field=models.SmallIntegerField(default=1, help_text='The current status of this upload. Possible values are: (1): Awaiting processing in queue., (2): Item processed successfully., (3): Item encountered an error while processing., (4): Item is currently being processed., (5): Item failed processing, but will be retried., (6): Item failed validity tests.', choices=[(1, 'Awaiting processing in queue.'), (2, 'Item processed successfully.'), (3, 'Item encountered an error while processing.'), (4, 'Item is currently being processed.'), (5, 'Item failed processing, but will be retried.'), (6, 'Item failed validity tests.')]),
        ),
    ]
