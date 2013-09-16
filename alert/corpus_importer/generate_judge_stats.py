import datetime
import pickle
import pprint
import simplejson
from threading import Thread
import traceback
import argparse

from datetime import date, timedelta
import time
import sys
from alert.corpus_importer.import_law_box import get_html_from_raw_text, get_judge, get_court_object
from alert.search.models import Court


DEBUG = 4

##########################################
# This variable is used to do statistical work on Opinions whose jurisdiction is unclear. The problem is that
# many Opinions, probably thousands of them, have a court like, "D. Wisconsin." Well, Wisconsin has an east and
# west district, but no generic district, so this has to be resolved. When we hit such a case, we set it aside
# for later processing, once we've processed all the easy cases. At that point, we will have the variable below,
# judge stats, which will have all of the judges along with a count of their jurisdictions:
# judge_stats = {
#     'McKensey': {
#         'wied': 998,
#         'wis': 2
#     }
# }
# So in this case, you can see quite clearly that McKensey is a judge at wied, and we can classify the case as
# such.
##########################################
try:
    with open('judge_stats.pkl', 'rb') as fix_file:
        judge_stats = pickle.load(fix_file)
except (IOError, EOFError):
    judge_stats = {}

all_courts = Court.objects.all()


def get_judge_and_court(case_path):
    raw_text = open(case_path).read()
    clean_html_tree, complete_html_tree, clean_html_str, body_text = get_html_from_raw_text(raw_text)
    judge = get_judge(clean_html_tree, case_path)
    court = get_court_object(clean_html_tree, case_path=case_path)
    if judge in judge_stats:
        if court in judge_stats[judge]:
            judge_stats[judge][court] += 1
        else:
            judge_stats[judge][court] = 1
    else:
        judge_stats[judge] = {court: 1}


def main():
    parser = argparse.ArgumentParser(description='Import the corpus provided by lawbox')
    parser.add_argument('-f', '--file', type=str, default="index.txt", required=False, dest="file_name",
                        help="The file that has all the URLs to import, one per line.")
    parser.add_argument('-l', '--line', type=int, default=1, required=False,
                        help='If provided, this will be the line number in the index file where we resume processing.')
    parser.add_argument('-r', '--resume', default=False, required=False, action='store_true',
                        help='Use the saved marker to resume operation where it last failed.')
    args = parser.parse_args()

    def case_generator(line_number):
        """Yield cases from the index file."""
        index_file = open(args.file_name)
        for i, line in enumerate(index_file):
            if i > line_number:
                yield line.strip()

    if args.resume:
        with open('lawbox_progress_marker_judge_stat_generator.txt') as marker:
            resume_point = int(marker.read().strip())
        cases = case_generator(resume_point)
        i = resume_point
    else:
        cases = case_generator(args.line)
        i = args.line

    t1 = time.time()
    timings = []
    for case_path in cases:
        if i % 1000 == 1:
            t1 = time.time()
        if DEBUG >= 2 and i % 1000 == 0:
            t2 = time.time()
            timings.append(t2 - t1)
            average_per_s = 1000 / (sum(timings) / float(len(timings)))

            print "\nCompleted 1000 cases in %0.1f seconds (average: %0.1f/s, %0.1f/m, %0.1f/h)" % \
                                        ((t2 - t1), average_per_s, average_per_s * 60, average_per_s * 60 * 60)
            print "%s: Doing case (%s): file://%s" % (datetime.datetime.now(), i, case_path)

        try:
            doc = get_judge_and_court(case_path)
            i += 1
        except:
            print "Last case was number %s: %s" % (i, case_path)
            with open('lawbox_progress_marker_judge_stat_generator.txt', 'w') as marker:
                marker.write(str(i))
            with open('judge_stats.pkl', 'wb') as fix_file:
                pickle.dump(judge_stats, fix_file)
            with open('judge_stats.py', 'wb') as stats_file:
                pprint.pprint(judge_stats, stream=stats_file, indent=4)
            raise

    with open('lawbox_progress_marker_judge_stat_generator.txt', 'w') as marker:
        marker.write(str(i))
    with open('judge_stats.pkl', 'wb') as fix_file:
        pickle.dump(judge_stats, fix_file)
    with open('judge_stats.py', 'wb') as stats_file:
        pprint.pprint(judge_stats, stream=stats_file, indent=4)

if __name__ == '__main__':
    main()
