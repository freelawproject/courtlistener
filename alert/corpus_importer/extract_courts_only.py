import subprocess
import traceback
from alert.corpus_importer.import_law_box import (
    get_court_object, get_citations_from_tree, get_html_from_raw_text
)
import datetime


DEBUG = [
    'counter',
    'review_court_issues',
    'log_bad_courts',
]


def import_law_box_case(case_path):
    raw_text = open(case_path).read()
    clean_html_tree, complete_html_tree, clean_html_str, body_text = get_html_from_raw_text(raw_text)
    citations = get_citations_from_tree(complete_html_tree, case_path)
    court = get_court_object(clean_html_tree, citations, case_path)

    if not court and 'review_court_issues' in DEBUG:
        if 'review_court_issues' in DEBUG:
            subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
            raw_input("No court identified! Can we fix this and restart, or just press enter to log it? ")
        if 'log_bad_courts' in DEBUG:
            # Write the failed case out to file.
            with open('missing_courts_post_focus.txt', 'a') as out:
                out.write('%s\n' % case_path)


def case_generator(line_number):
    """Yield cases from the index file."""
    index_file = open('missing_courts.txt', 'r')
    for i, line in enumerate(index_file):
        if i > line_number:
            yield line.strip()


def main():
    with open('lawbox_extract_courts_progress_marker.txt') as marker:
        resume_point = int(marker.read().strip())
        cases = case_generator(resume_point)
        i = resume_point

    for case_path in cases:
        if 'counter' in DEBUG:
            print "\n%s: Doing case (%s): file://%s" % (datetime.datetime.now(), i, case_path)
        try:
            import_law_box_case(case_path)
            i += 1
        finally:
            traceback.format_exc()
            with open('lawbox_extract_courts_progress_marker.txt', 'w') as marker:
                marker.write(str(i))

if __name__ == '__main__':
    main()
