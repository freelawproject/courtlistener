# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def populate_pacer_court_id(apps, schema_editor):
    Court = apps.get_model('search', 'Court')
    data = {
        'vib': 192, 'ilsd': 69, 'tnwd': 171, 'ilsb': 68, 'tnwb': 170,
        'scd': 163, 'tnmb': 168, 'scb': 162, 'ganb': 54, 'miwb': 98,
        'gand': 55, 'miwd': 99, 'mnb': 100, 'flsd': 51, 'mnd': 101,
        'flsb': 50, 'vtb': 184, 'vtd': 185, 'ksd': 79, 'moed': 107, 'wvsb': 200,
        'wvsd': 201, 'flmb': 46, 'flmd': 47, 'nyeb': 122, 'nvd': 115,
        'nyed': 123, 'gamb': 52, 'almd': 17, 'gub': 58, 'almb': 16,
        'wawd': 197, 'okwb': 148, 'gud': 59, 'okwd': 149, 'msnb': 102,
        'txwd': 181, 'oknb': 146, 'oknd': 147, 'msnd': 103, 'txwb': 180,
        'njb': 118, 'ncwb': 134, 'nynb': 124, 'ncwd': 135, 'nynd': 125,
        'njd': 119, 'mdb': 92, 'wawb': 196, 'mdd': 93, 'iasb': 76, 'arb': 24,
        'innd': 71, 'innb': 70, 'iasd': 77, 'ohnd': 141, 'ohnb': 140,
        'alnd': 19, 'ned': 113, 'mieb': 96, 'mied': 97, 'alnb': 18, 'med': 91,
        'paed': 153, 'paeb': 152, 'meb': 90, 'dcd': 45, 'mowb': 108, 'dcb': 44,
        'mowd': 109, 'nmd': 121, 'nmb': 120, 'ord': 151, 'orb': 150,
        'vaeb': 188, 'vaed': 189, 'nywd': 129, 'ndb': 136, 'nywb': 128,
        'ndd': 137, 'ctd': 41, 'cob': 38, 'cod': 39, 'ctb': 40, 'akb': 22,
        'idd': 63, 'kywb': 82, 'idb': 62, 'kywd': 83, 'akd': 23, 'iand': 75,
        'nhd': 117, 'ianb': 74, 'mssb': 104, 'vid': 193, 'nhb': 116,
        'nysb': 126, 'pamd': 155, 'nysd': 127, 'ared': 27, 'wied': 203,
        'areb': 26, 'wieb': 202, 'moeb': 106, 'pamb': 154, 'kyed': 81,
        'mssd': 105, 'flnb': 48, 'txed': 175, 'flnd': 49, 'txeb': 174,
        'ilcd': 65, 'ksb': 78, 'sdd': 165, 'tnmd': 169, 'sdb': 164, 'cacb': 973,
        'vawd': 191, 'vawb': 190, 'utb': 182, 'casd': 37, 'utd': 183,
        'casb': 36, 'ilnb': 66, 'azd': 25, 'mtb': 110, 'tned': 167, 'deb': 42,
        'txsb': 178, 'ded': 43, 'txsd': 179, 'mtd': 111, 'tneb': 166,
        'ilcb': 64, 'prd': 159, 'cand': 35, 'canb': 34, 'prb': 158,
        'arwd': 29, 'pawb': 156, 'pawd': 157, 'wiwd': 205, 'rid': 161,
        'rib': 160, 'wiwb': 204, 'lamb': 86, 'wvnb': 198, 'wvnd': 199,
        'lamd': 87, 'okeb': 144, 'arwb': 28, 'ohsb': 142, 'wyd': 207,
        'ohsd': 143, 'laeb': 84, 'alsd': 21, 'alsb': 20, 'laed': 85,
        'insb': 72, 'insd': 73, 'kyeb': 80, 'gasb': 56, 'gasd': 57, 'caeb': 32,
        'mab': 94, 'mad': 95, 'caed': 33, 'waed': 195, 'nebraskab': 112,
        'waeb': 194, 'oked': 145, 'txnb': 176, 'ilnd': 67, 'ncmd': 133,
        'ncmb': 132, 'txnd': 177, 'cacd': 31, 'lawd': 89, 'hib': 60, 'lawb': 88,
        'nmib': 138, 'gamd': 53, 'nmid': 139, 'wyb': 206, 'hid': 61,
        'nced': 131, 'nceb': 130, 'nvb': 114,
    }
    for k, v in data.items():
        Court.objects.filter(pk=k).update(pacer_court_id=v)


class Migration(migrations.Migration):

    dependencies = [
        ('search', '0051_court_pacer_court_id'),
    ]

    operations = [
        migrations.RunPython(populate_pacer_court_id),
    ]
