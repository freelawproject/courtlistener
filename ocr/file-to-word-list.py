'''
A simple script that will take in a text file filled with words and
punctuation, and then output each word with its document count, ordered by
count.

The input file must be named file.txt.

The output will be printed as follows:
14,the
12,of
9,happy
1,ostrich
'''

import re

f = open('file.txt', 'r')

# Build a big list of the words.
unsorted_list = []
for line in f:
    hits = re.findall(r'\b[^\W\d_]+\b', line)
    for hit in hits:
        unsorted_list.append(hit)

f.close()

# Count and uniquify the list
# Output will be a list of lists, of the form:
# [('1', 4), ('3', 2), ('2', 1), ('4', 1)]
# Not sorted yet.
# counted_list = [(a, unsorted_list.count(a)) for a in set(unsorted_list)]

# Sort the list
# sorted_list = sorted(counted_list, key=lambda x: -x[1])

# Memory optimized version of the above, in theory.
sorted_list = sorted([(a, unsorted_list.count(a)) for a in set(unsorted_list)],
    key=lambda x: -x[1])

for tuple in sorted_list:
    print str(tuple[1]) + ',' + tuple[0]
