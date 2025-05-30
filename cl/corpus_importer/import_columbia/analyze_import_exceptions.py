"""
Created on Thu Jun 16 14:31:21 2016

@author: elliott
"""

import os
import re
from collections import Counter, defaultdict

os.chdir("/home/elliott/freelawmachine/flp/columbia_data/logs/2")
currfile = ""
courtid_tab: Counter = Counter()
cite_tab: Counter = Counter()
court_cite_tab: Counter = Counter()
printline = False
file_lists: defaultdict = defaultdict(list)
for line in open("import_columbia_output_stage_2.log"):
    if "exception in file" in line:
        i = line.find("opinions/") + len("opinions/")
        j = line.rfind("'")
        currfile = line[i:j]
        court = currfile.split("/documents")[0]

    if "Exception:" in line:
        if "date" not in line:
            print(line)
        print(f"{line}\n", end="", file=open("unknown.txt", "a"))
        # file_lists[line].append(currfile)
        # print(line)

    if printline:
        print(line)
        printline = False

    if "Known exception in file" in line:
        printline = True

    if "Failed to get a citation" in line:
        seg = line.split("'")[1]

        newseg = re.sub(r"\d", "#", seg)
        # print(newseg)
        # if 'Ct. Sup.' not in newseg:
        #    if 'Ohio App.' not in newseg:
        #        if 'Okla. Cr.' not in newseg:
        cite_tab[newseg] += 1
        court_cite_tab[court, newseg] += 1

    if "Failed to find a court ID" in line:
        seg = line.split('"')[1]

        courtid_tab[court, seg] += 1

cite_tab.most_common()

courtid_tab.most_common()
