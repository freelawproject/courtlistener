# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2020-08-07 21:44


from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0096_add_court_fields_and_noops'),
        ('favorites', '0005_add_user_tag_and_prayers_tables'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocketTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('docket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='docket_tags', to='search.Docket')),
            ],
        ),
        migrations.RemoveField(
            model_name='usertag',
            name='content_type',
        ),
        migrations.RemoveField(
            model_name='usertag',
            name='object_id',
        ),
        migrations.AddField(
            model_name='dockettag',
            name='tag',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='docket_tags', to='favorites.UserTag'),
        ),
        migrations.AddField(
            model_name='usertag',
            name='dockets',
            field=models.ManyToManyField(blank=True, help_text='Dockets that are tagged with by this item', related_name='user_tags', through='favorites.DocketTag', to='search.Docket'),
        ),
        migrations.AlterUniqueTogether(
            name='dockettag',
            unique_together=set([('docket', 'tag')]),
        ),
    ]
