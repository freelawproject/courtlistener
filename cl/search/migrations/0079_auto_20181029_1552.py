# -*- coding: utf-8 -*-


from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0078_convert_page_to_str'),
    ]

    operations = [
        migrations.AddField(
            model_name='recapdocument',
            name='is_sealed',
            field=models.NullBooleanField(help_text='Is this item sealed or otherwise unavailable on PACER?', db_index=True),
        ),
        migrations.AlterField(
            model_name='citation',
            name='type',
            field=models.SmallIntegerField(help_text='The type of citation that this is.', choices=[(1, 'A federal reporter citation (e.g. 5 F. 55)'), (2, 'A citation in a state-based reporter (e.g. Alabama Reports)'), (3, 'A citation in a regional reporter (e.g. Atlantic Reporter)'), (4, "A citation in a specialty reporter (e.g. Lawyers' Edition)"), (5, 'A citation in an early SCOTUS reporter (e.g. 5 Black. 55)'), (6, 'A citation in the Lexis system (e.g. 5 LEXIS 55)'), (7, 'A citation in the WestLaw system (e.g. 5 WL 55)'), (8, 'A vendor neutral citation (e.g. 2013 FL 1)')]),
        ),
        migrations.AlterField(
            model_name='docket',
            name='ia_date_first_change',
            field=models.DateTimeField(help_text='The moment when this item first changed and was marked as needing an upload. Used for determining when to upload an item.', null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='docketentry',
            name='entry_number',
            field=models.BigIntegerField(help_text='# on the PACER docket page. For appellate cases, this may be the internal PACER ID for the document, when an entry ID is otherwise unavailable.'),
        ),
    ]
