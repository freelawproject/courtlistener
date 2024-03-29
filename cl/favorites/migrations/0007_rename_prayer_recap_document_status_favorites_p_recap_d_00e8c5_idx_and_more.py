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
            new_name="favorites_p_recap_d_00e8c5_idx",
            old_fields=("recap_document", "status"),
        ),
        migrations.RenameIndex(
            model_name="prayer",
            new_name="favorites_p_date_cr_8bf054_idx",
            old_fields=("date_created", "user", "status"),
        ),
        migrations.RenameIndex(
            model_name="prayer",
            new_name="favorites_p_recap_d_7c046c_idx",
            old_fields=("recap_document", "user"),
        ),
        migrations.RenameIndex(
            model_name="usertag",
            new_name="favorites_u_user_id_f6c9a6_idx",
            old_fields=("user", "name"),
        ),
    ]
