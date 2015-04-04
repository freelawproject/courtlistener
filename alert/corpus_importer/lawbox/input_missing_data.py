import datetime
import pickle

from alert.corpus_importer.dup_helpers import get_html_from_raw_text
from alert.corpus_importer.lawbox.import_law_box import get_citations_from_tree


DEBUG = [
    'counter',
    'review_issues',
    #'log_bad_values',
]

try:
    with open('lawbox_fix_file.pkl', 'rb') as fix_file:
        fixes = pickle.load(fix_file)
except (IOError, EOFError):
    fixes = {}


def add_fix(case_path, fix_dict):
    """Adds a fix to the fix dictionary. This dictionary looks like:

    fixes = {
        'path/to/some/case.html': {'docket_number': None, 'date_filed': date(1982, 6, 9)},
    }
    """
    if case_path in fixes:
        fixes[case_path].update(fix_dict)
    else:
        fixes[case_path] = fix_dict


def import_law_box_case(case_path, i):
    raw_text = open(case_path).read()
    clean_html_tree, complete_html_tree, clean_html_str, body_text = get_html_from_raw_text(raw_text)
    citations = get_citations_from_tree(complete_html_tree, case_path)
    if not citations:
        print "******** F: %s ********" % case_path

    """
    #court = get_court_object(clean_html_tree, citations, case_path)
    #dates = get_date_filed(clean_html_tree, citations, case_path=case_path, court=court)
    try:
        dates = fixes[case_path]['dates']
    except KeyError:
        if not citations:
            subprocess.Popen(['firefox', 'file://%s' % case_path], shell=False).communicate()
            input_date = raw_input('  No date found. What should be here (YYYY-MM-DD)? ')
            add_fix(case_path, {'dates': [datetime.datetime.strptime(input_date, '%Y-%m-%d').date()]})
            with open('lawbox_progress_marker_input_data.txt', 'w') as marker:
                marker.write(str(i))
            with open('lawbox_fix_file.pkl', 'wb') as fix_file:
                pickle.dump(fixes, fix_file)
    """


def case_generator(line_number):
    """Yield cases from the index file."""
    index_file = open('missing_citations.txt', 'r')
    for i, line in enumerate(index_file):
        if i > line_number:
            yield line.strip()


def main():
    with open('lawbox_progress_marker_input_data.txt') as marker:
        resume_point = int(marker.read().strip())
        cases = case_generator(resume_point)
        i = resume_point

    for case_path in cases:
        if 'counter' in DEBUG:
            print "\n%s: Doing case (%s): file://%s" % (datetime.datetime.now(), i, case_path)
        import_law_box_case(case_path, i)
        i += 1



if __name__ == '__main__':
    main()
