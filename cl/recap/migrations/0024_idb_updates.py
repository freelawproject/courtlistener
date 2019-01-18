# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recap', '0023_auto_20181119_2052'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='fjcintegrateddatabase',
            name='case_name',
        ),
        migrations.RemoveField(
            model_name='fjcintegrateddatabase',
            name='pacer_case_id',
        ),
        migrations.AlterField(
            model_name='fjcintegrateddatabase',
            name='nature_of_suit',
            field=models.IntegerField(blank=True, help_text=b'A three digit statistical code representing the nature of suit of the action filed.', null=True, choices=[(110, b'Insurance'), (120, b'Marine contract actions'), (130, b'Miller act'), (140, b'Negotiable instruments'), (150, b'Overpayments & enforcement of judgments'), (151, b'Overpayments under the medicare act'), (152, b'Recovery of defaulted student loans'), (153, b'Recovery of overpayments of vet benefits'), (160, b"Stockholder's suits"), (190, b'Other contract actions'), (195, b'Contract product liability'), (196, b'Contract franchise'), (210, b'Land condemnation'), (220, b'Foreclosure'), (230, b'Rent, lease, ejectment'), (240, b'Torts to land'), (245, b'Tort product liability'), (290, b'Other real property actions'), (310, b'Airplane personal injury'), (315, b'Airplane product liability'), (320, b'Assault, libel, and slander'), (330, b"Federal employers' liability"), (340, b'Marine personal injury'), (345, b'Marine - Product liability'), (350, b'Motor vehicle personal injury'), (355, b'Motor vehicle product liability'), (360, b'Other personal liability'), (362, b'Medical malpractice'), (365, b'Personal injury - Product liability'), (367, b'Health care / pharm'), (368, b'Asbestos personal injury - Prod. Liab.'), (370, b'Other fraud'), (371, b'Truth in lending'), (375, b'False Claims Act'), (380, b'Other personal property damage'), (385, b'Property damage - Product liability'), (400, b'State re-appointment'), (410, b'Antitrust'), (422, b'Bankruptcy appeals rule 28 USC 158'), (423, b'Bankruptcy withdrawal 28 USC 157'), (430, b'Banks and banking'), (440, b'Civil rights other'), (441, b'Civil rights voting'), (442, b'Civil rights jobs'), (443, b'Civil rights accomodations'), (444, b'Civil rights welfare'), (445, b'Civil rights ADA employment'), (446, b'Civil rights ADA other'), (448, b'Education'), (450, b'Interstate commerce'), (460, b'Deportation'), (462, b'Naturalization, petition for hearing of denial'), (463, b'Habeas corpus - alien detainee'), (465, b'Other immigration actions'), (470, b'Civil (RICO)'), (480, b'Consumer credit'), (490, b'Cable/Satellite TV'), (510, b'Prisoner petitions - vacate sentence'), (530, b'Prisoner petitions - habeas corpus'), (535, b'Habeas corpus: Death penalty'), (540, b'Prisoner petitions - mandamus and other'), (550, b'Prisoner - civil rights'), (555, b'Prisoner - prison condition'), (560, b'Civil detainee'), (610, b'Agricultural acts'), (620, b'Food and drug acts'), (625, b'Drug related seizure of property'), (630, b'Liquor laws'), (640, b'Railroad and trucks'), (650, b'Airline regulations'), (660, b'Occupational safety/health'), (690, b'Other forfeiture and penalty suits'), (710, b'Fair Labor Standards Act'), (720, b'Labor/Management Relations Act'), (730, b'Labor/Management report & disclosure'), (740, b'Railway Labor Act'), (751, b'Family and Medical Leave Act'), (790, b'Other labor litigation'), (791, b'Employee Retirement Income Security Act'), (810, b'Selective service'), (820, b'Copyright'), (830, b'Patent'), (840, b'Trademark'), (850, b'Securities, Commodities, Exchange'), (860, b'Social security'), (861, b'HIA (1395 FF) / Medicare'), (862, b'Black lung'), (863, b'D.I.W.C. / D.I.W.W.'), (864, b'S.S.I.D.'), (865, b'R.S.I.'), (870, b'Tax suits'), (871, b'IRS 3rd party suits 26 USC 7609'), (875, b'Customer challenge 12 USC 3410'), (890, b'Other statutory actions'), (891, b'Agricultural acts'), (892, b'Economic Stabilization Act'), (893, b'Environmental matters'), (894, b'Energy Allocation Act'), (895, b'Freedom of Information Act of 1974'), (896, b'Arbitration'), (899, b'Administrative procedure act / review or appeal of agency decision'), (900, b'Appeal of fee - equal access to justice'), (910, b'Domestic relations'), (920, b'Insanity'), (930, b'Probate'), (940, b'Substitute trustee'), (950, b'Constitutionality of state statutes'), (990, b'Other'), (992, b'Local jurisdictional appeal'), (999, b'Miscellaneous')]),
        ),
    ]
