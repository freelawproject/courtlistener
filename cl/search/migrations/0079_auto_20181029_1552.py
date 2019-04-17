# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0078_convert_page_to_str'),
    ]

    operations = [
        migrations.AddField(
            model_name='recapdocument',
            name='is_sealed',
            field=models.NullBooleanField(help_text=b'Is this item sealed or otherwise unavailable on PACER?', db_index=True),
        ),
        migrations.AlterField(
            model_name='citation',
            name='type',
            field=models.SmallIntegerField(help_text=b'The type of citation that this is.', choices=[(1, b'A federal reporter citation (e.g. 5 F. 55)'), (2, b'A citation in a state-based reporter (e.g. Alabama Reports)'), (3, b'A citation in a regional reporter (e.g. Atlantic Reporter)'), (4, b"A citation in a specialty reporter (e.g. Lawyers' Edition)"), (5, b'A citation in an early SCOTUS reporter (e.g. 5 Black. 55)'), (6, b'A citation in the Lexis system (e.g. 5 LEXIS 55)'), (7, b'A citation in the WestLaw system (e.g. 5 WL 55)'), (8, b'A vendor neutral citation (e.g. 2013 FL 1)')]),
        ),
        migrations.AlterField(
            model_name='docket',
            name='ia_date_first_change',
            field=models.DateTimeField(help_text=b'The moment when this item first changed and was marked as needing an upload. Used for determining when to upload an item.', null=True, db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='docketentry',
            name='entry_number',
            field=models.BigIntegerField(help_text=b'# on the PACER docket page. For appellate cases, this may be the internal PACER ID for the document, when an entry ID is otherwise unavailable.'),
        ),
    ]
