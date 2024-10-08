# Generated by Django 4.2 on 2023-05-02 00:26

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            "favorites",
            "0006_remove_note_update_or_delete_snapshot_update_and_more",
        ),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="prayer",
            new_name="favorites_prayer_recap_document_id_status_82e2dbbb_idx",
            old_fields=("recap_document", "status"),
        ),
        migrations.RenameIndex(
            model_name="prayer",
            new_name="favorites_prayer_date_created_user_id_status_880d7280_idx",
            old_fields=("date_created", "user", "status"),
        ),
        migrations.RenameIndex(
            model_name="prayer",
            new_name="favorites_prayer_recap_document_id_user_id_c5d30108_idx",
            old_fields=("recap_document", "user"),
        ),
        migrations.RenameIndex(
            model_name="usertag",
            new_name="favorites_usertag_user_id_name_54aef6fe_idx",
            old_fields=("user", "name"),
        ),
    ]
