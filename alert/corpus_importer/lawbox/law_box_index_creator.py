"""This little script was used to generate a plaintext file containing all of the paths to all cases. Using that will be
more efficient than using a generator expression each time, since it will allow the program to crash and for us to
re-start the program at arbitrary places.
"""

import fnmatch
import os


def case_generator(dir_root):
    """Yield cases, one by one to the importer by recursing and iterating the import directory"""
    for root, dirnames, filenames in os.walk(dir_root):
        for filename in fnmatch.filter(filenames, '*'):
            yield os.path.join(root, filename)

with open('index.txt', 'w') as index:
    for case_path in case_generator('/sata/lawbox/dump/'):
        index.write('%s\n' % case_path)
