"""This is an experiment to see how well we can automate figuring out the
document types of CA9 briefs created at public.resource.org.

Basic idea is to go through a text file full of briefs and sort them into more
sane types of documents.

Pretty prints a dict of the findings once complete.

This is a TDD method for finding and sorting doc types.
"""

import re
from pprint import pprint


doc_types = {
    'apostles': [],
    'brief': [],
    'transcript': [],
    'petition': [],
    'motion': [],
    'memorandum': [],
    'unknown': [],
    'unknowable': [],
    'zzstats': {
        'apostles': 0,
        'brief': 0,
        'transcript': 0,
        'petition': 0,
        'motion': 0,
        'memorandum': 0,
        'unknowable': 0,
        'unknown': 0,
        'total': 0,
    },
}

with open('document_types.txt', 'r') as f:
    for line in f:
        line = line.lower()
        doc_types['zzstats']['total'] += 1
        if 'apostles' in line:
            doc_types['zzstats']['apostles'] += 1
            doc_types['apostles'].append(line)
        elif 'brief' in line:
            doc_types['zzstats']['brief'] += 1
            doc_types['brief'].append(line)
        elif 'motion' in line:
            doc_types['zzstats']['motion'] += 1
            doc_types['motion'].append(line)
        elif 'memorandum' in line:
            doc_types['zzstats']['memorandum'] += 1
            doc_types['memorandum'].append(line)
        elif re.search('petition', line):
            doc_types['zzstats']['petition'] += 1
            doc_types['petition'].append(line)
        elif re.search('transc?rr?ipt', line) or \
                re.search('argument', line):
            doc_types['zzstats']['transcript'] += 1
            doc_types['transcript'].append(line)

        # We can't figure it out yet or ever
        elif 'illegible' in line or 'no document name' in line:
            doc_types['zzstats']['unknowable'] += 1
            doc_types['unknowable'].append(line)
        else:
            doc_types['unknown'].append(line)
            doc_types['zzstats']['unknown'] += 1

pprint(doc_types)
