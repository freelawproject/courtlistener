# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

fixtures = ['fjc_court_ids']

fjc_district_ids = {
    u'akb': u'7-', u'akd': u'7-', u'almb': u'27', u'almd': u'27',
    u'alnb': u'26', u'alnd': u'26', u'alsb': u'28', u'alsd': u'28',
    u'arb': u'70', u'areb': u'60', u'ared': u'60', u'arwb': u'61',
    u'arwd': u'61', u'azd': u'70', u'cacb': u'73', u'cacd': u'73',
    u'caeb': u'72', u'caed': u'72', u'canb': u'71', u'cand': u'71',
    u'casb': u'74', u'casd': u'74', u'cob': u'82', u'cod': u'82', u'ctb': u'05',
    u'ctd': u'05', u'dcb': u'90', u'dcd': u'90', u'deb': u'11', u'ded': u'11',
    u'flmb': u'3A', u'flmd': u'3A', u'flnb': u'29', u'flnd': u'29',
    u'flsb': u'3C', u'flsd': u'3C', u'gamb': u'3G', u'gamd': u'3G',
    u'ganb': u'3E', u'gand': u'3E', u'gasb': u'3J', u'gasd': u'3J',
    u'gub': u'93', u'gud': u'93', u'hib': u'75', u'hid': u'75', u'ianb': u'62',
    u'iand': u'62', u'iasb': u'63', u'iasd': u'63', u'idb': u'76',
    u'idd': u'76', u'ilcb': u'53', u'ilcd': u'53', u'ilnb': u'52',
    u'ilnd': u'52', u'ilsb': u'54', u'ilsd': u'54', u'innb': u'55',
    u'innd': u'55', u'insb': u'56', u'insd': u'56', u'ksb': u'83',
    u'ksd': u'83', u'kyeb': u'43', u'kyed': u'43', u'kywb': u'44',
    u'kywd': u'44', u'laeb': u'3L', u'laed': u'3L', u'lamb': u'3N',
    u'lamd': u'3N', u'lawb': u'36', u'lawd': u'36', u'mab': u'01',
    u'mad': u'01', u'mdb': u'16', u'mdd': u'16', u'meb': u'00', u'med': u'00',
    u'mieb': u'45', u'mied': u'45', u'miwb': u'46', u'miwd': u'46',
    u'mnb': u'64', u'mnd': u'64', u'moeb': u'65', u'moed': u'65',
    u'mowb': u'66', u'mowd': u'66', u'msnb': u'37', u'msnd': u'37',
    u'mssb': u'38', u'mssd': u'38', u'mtb': u'77', u'mtd': u'77',
    u'nceb': u'17', u'nced': u'17', u'ncmb': u'18', u'ncmd': u'18',
    u'ncwb': u'19', u'ncwd': u'19', u'ndb': u'68', u'ndd': u'68', u'neb': u'67',
    u'ned': u'67', u'nhb': u'02', u'nhd': u'02', u'njb': u'12', u'njd': u'12',
    u'nmb': u'84', u'nmd': u'84', u'nmib': u'94', u'nmid': u'94', u'nvb': u'78',
    u'nvd': u'78', u'nyeb': u'07', u'nyed': u'07', u'nynb': u'06',
    u'nynd': u'06', u'nysb': u'08', u'nysd': u'08', u'nywb': u'09',
    u'nywd': u'09', u'ohnb': u'47', u'ohnd': u'47', u'ohsb': u'48',
    u'ohsd': u'48', u'okeb': u'86', u'oked': u'86', u'oknb': u'85',
    u'oknd': u'85', u'okwb': u'87', u'okwd': u'87', u'orb': u'79',
    u'ord': u'79', u'paeb': u'13', u'paed': u'13', u'pamb': u'14',
    u'pamd': u'14', u'pawb': u'15', u'pawd': u'15', u'prb': u'04',
    u'prd': u'04', u'rib': u'03', u'rid': u'03', u'scb': u'20', u'scd': u'20',
    u'sdb': u'69', u'sdd': u'69', u'tneb': u'49', u'tned': u'49',
    u'tnmb': u'50', u'tnmd': u'50', u'tnwb': u'51', u'tnwd': u'51',
    u'txeb': u'40', u'txed': u'40', u'txnb': u'39', u'txnd': u'39',
    u'txsb': u'41', u'txsd': u'41', u'txwb': u'42', u'txwd': u'42',
    u'utb': u'88', u'utd': u'88', u'vaeb': u'22', u'vaed': u'22',
    u'vawb': u'23', u'vawd': u'23', u'vib': u'91', u'vid': u'91', u'vtb': u'10',
    u'vtd': u'10', u'waeb': u'80', u'waed': u'80', u'wawb': u'81',
    u'wawd': u'81', u'wieb': u'57', u'wied': u'57', u'wiwb': u'58',
    u'wiwd': u'58', u'wvnb': u'24', u'wvnd': u'24', u'wvsb': u'25',
    u'wvsd': u'25', u'wyb': u'89', u'wyd': u'89'
}
fjc_circuit_ids = {
    u'ca1': '1', u'ca2': '2', u'ca3': '3', u'ca4': '4', u'ca5': '5',
    u'ca6': '6', u'ca7': '7', u'ca8': '8', u'ca9': '9', u'ca10': '10',
    u'ca11': '11', u'cadc': '0',
}


def add_fjc_ids(apps, schema_editor):
    Court = apps.get_model('search', 'Court')
    # Merge the two dicts, then update the DB.
    fjc_district_ids.update(fjc_circuit_ids)
    for k, v in fjc_district_ids.items():
        Court.objects.filter(pk=k).update(fjc_court_id=v)


def blank_fjc_ids(apps, schema_editor):
    Court = apps.get_model('search', 'Court')
    Court.objects.all().update(fjc_court_id='')


class Migration(migrations.Migration):
    dependencies = [
        ('search', '0055_court_fjc_court_id'),
    ]

    operations = [
        migrations.RunPython(add_fjc_ids, reverse_code=blank_fjc_ids),
    ]
