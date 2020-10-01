# -*- coding: utf-8 -*-


from django.db import migrations

fixtures = ['fjc_court_ids']

fjc_district_ids = {
    'akb': '7-', 'akd': '7-', 'almb': '27', 'almd': '27',
    'alnb': '26', 'alnd': '26', 'alsb': '28', 'alsd': '28',
    'arb': '70', 'areb': '60', 'ared': '60', 'arwb': '61',
    'arwd': '61', 'azd': '70', 'cacb': '73', 'cacd': '73',
    'caeb': '72', 'caed': '72', 'canb': '71', 'cand': '71',
    'casb': '74', 'casd': '74', 'cob': '82', 'cod': '82', 'ctb': '05',
    'ctd': '05', 'dcb': '90', 'dcd': '90', 'deb': '11', 'ded': '11',
    'flmb': '3A', 'flmd': '3A', 'flnb': '29', 'flnd': '29',
    'flsb': '3C', 'flsd': '3C', 'gamb': '3G', 'gamd': '3G',
    'ganb': '3E', 'gand': '3E', 'gasb': '3J', 'gasd': '3J',
    'gub': '93', 'gud': '93', 'hib': '75', 'hid': '75', 'ianb': '62',
    'iand': '62', 'iasb': '63', 'iasd': '63', 'idb': '76',
    'idd': '76', 'ilcb': '53', 'ilcd': '53', 'ilnb': '52',
    'ilnd': '52', 'ilsb': '54', 'ilsd': '54', 'innb': '55',
    'innd': '55', 'insb': '56', 'insd': '56', 'ksb': '83',
    'ksd': '83', 'kyeb': '43', 'kyed': '43', 'kywb': '44',
    'kywd': '44', 'laeb': '3L', 'laed': '3L', 'lamb': '3N',
    'lamd': '3N', 'lawb': '36', 'lawd': '36', 'mab': '01',
    'mad': '01', 'mdb': '16', 'mdd': '16', 'meb': '00', 'med': '00',
    'mieb': '45', 'mied': '45', 'miwb': '46', 'miwd': '46',
    'mnb': '64', 'mnd': '64', 'moeb': '65', 'moed': '65',
    'mowb': '66', 'mowd': '66', 'msnb': '37', 'msnd': '37',
    'mssb': '38', 'mssd': '38', 'mtb': '77', 'mtd': '77',
    'nceb': '17', 'nced': '17', 'ncmb': '18', 'ncmd': '18',
    'ncwb': '19', 'ncwd': '19', 'ndb': '68', 'ndd': '68', 'neb': '67',
    'ned': '67', 'nhb': '02', 'nhd': '02', 'njb': '12', 'njd': '12',
    'nmb': '84', 'nmd': '84', 'nmib': '94', 'nmid': '94', 'nvb': '78',
    'nvd': '78', 'nyeb': '07', 'nyed': '07', 'nynb': '06',
    'nynd': '06', 'nysb': '08', 'nysd': '08', 'nywb': '09',
    'nywd': '09', 'ohnb': '47', 'ohnd': '47', 'ohsb': '48',
    'ohsd': '48', 'okeb': '86', 'oked': '86', 'oknb': '85',
    'oknd': '85', 'okwb': '87', 'okwd': '87', 'orb': '79',
    'ord': '79', 'paeb': '13', 'paed': '13', 'pamb': '14',
    'pamd': '14', 'pawb': '15', 'pawd': '15', 'prb': '04',
    'prd': '04', 'rib': '03', 'rid': '03', 'scb': '20', 'scd': '20',
    'sdb': '69', 'sdd': '69', 'tneb': '49', 'tned': '49',
    'tnmb': '50', 'tnmd': '50', 'tnwb': '51', 'tnwd': '51',
    'txeb': '40', 'txed': '40', 'txnb': '39', 'txnd': '39',
    'txsb': '41', 'txsd': '41', 'txwb': '42', 'txwd': '42',
    'utb': '88', 'utd': '88', 'vaeb': '22', 'vaed': '22',
    'vawb': '23', 'vawd': '23', 'vib': '91', 'vid': '91', 'vtb': '10',
    'vtd': '10', 'waeb': '80', 'waed': '80', 'wawb': '81',
    'wawd': '81', 'wieb': '57', 'wied': '57', 'wiwb': '58',
    'wiwd': '58', 'wvnb': '24', 'wvnd': '24', 'wvsb': '25',
    'wvsd': '25', 'wyb': '89', 'wyd': '89'
}
fjc_circuit_ids = {
    'ca1': '1', 'ca2': '2', 'ca3': '3', 'ca4': '4', 'ca5': '5',
    'ca6': '6', 'ca7': '7', 'ca8': '8', 'ca9': '9', 'ca10': '10',
    'ca11': '11', 'cadc': '0',
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
