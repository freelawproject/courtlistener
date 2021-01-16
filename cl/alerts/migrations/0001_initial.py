# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Alert',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=75, verbose_name='a name for the alert')),
                ('query', models.CharField(max_length=2500, verbose_name='the text of an alert created by a user')),
                ('rate', models.CharField(max_length=10, verbose_name='the rate chosen by the user for the alert', choices=[('rt', 'Real Time'), ('dly', 'Daily'), ('wly', 'Weekly'), ('mly', 'Monthly'), ('off', 'Off')])),
                ('always_send_email', models.BooleanField(default=False, verbose_name='Always send an alert?')),
                ('date_last_hit', models.DateTimeField(null=True, verbose_name='time of last trigger', blank=True)),
            ],
            options={
                'ordering': ['rate', 'query'],
            },
        ),
        migrations.CreateModel(
            name='RealTimeQueue',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_modified', models.DateTimeField(help_text='the last moment when the item was modified', auto_now=True, db_index=True)),
                ('item_type', models.CharField(help_text='the type of item this is, one of: o (Opinion), oa (Oral Argument)', max_length=3, db_index=True, choices=[('o', 'Opinion'), ('oa', 'Oral Argument')])),
                ('item_pk', models.IntegerField(help_text='the pk of the item')),
            ],
        ),
    ]
