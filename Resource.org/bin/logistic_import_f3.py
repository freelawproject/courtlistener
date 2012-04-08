# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#  Under Sections 7(a) and 7(b) of version 3 of the GNU Affero General Public
#  License, that license is supplemented by the following terms:
#
#  a) You are required to preserve this legal notice and all author
#  attributions in this program and its accompanying documentation.
#
#  b) You are prohibited from misrepresenting the origin of any material
#  within this covered work and you are required to mark in reasonable
#  ways how any modified versions differ from the original version.

import dup_finder
import f3_helpers
import argparse
import re

def generate_training_data():
    '''Make a CSV that can be imported by the train_classifier method.
    
    Iterate over the documents in the corpus and check them for duplicates. 
    If they have a likely duplicate
    '''
    corpus = f3_helpers.Corpus('file:///var/www/court-listener/Resource.org/data/F3/')
    vol_file = open('../logs/vol_file.txt', 'r+')
    case_file = open('../logs/case_file.txt', 'r+')
    stat_file = open('../logs/training_stats.csv', 'a')
    try:
        i = int(vol_file.readline())
        print "Vol: %s" % i
    except ValueError:
        # the volume file is emtpy or otherwise failing.
        i = 0
    vol_file.close()
    for volume in corpus[i:]:
        try:
            j = int(case_file.readline())
        except ValueError:
            j = 0
        case_file.close()
        for case in volume[j::10]:
            if f3_helpers.need_dup_check_for_date_and_court(case):
                print "Running dup check..."
                # stats takes the form: [count_from_search] or 
                #                       [count_from_search,
                #                        count_from_docket_num,
                #                        [case_name_diff_1, diff_2, diff_3, etc],
                #                        [content_length_percent_diff_1, 2, 3],
                #                        [content_diff_1, 2, 3]
                #                       ]
                # candidates is a list of 0 to n possible duplicates 
                stats, candidates = dup_finder.get_dup_stats(case)
                if len(candidates) == 0:
                    # None found. Therefore...
                    print "  No candidates found."
                    continue
                elif (re.sub("(\D|0)", "", case.docket_number) == \
                            re.sub("(\D|0)", "", candidates[0]['docketNumber'])) and \
                            (len(candidates) == 1):
                    # If the docket numbers are identical, and there was 
                    # only one result at that time...
                    print "  Match made on docket number of single candidate."
                    continue
                else:
                    # Possible duplicate, make stats for logistic regression.
                    print "STATS: %s" % stats
                    for i in range(0, len(candidates)):
                        if stats[2][i] < 0.2:
                            continue
                        print "  %s) Case name: %s" % (i + 1, case.case_name)
                        print "                %s" % candidates[i]['caseName']
                        print "      Docket nums: %s" % (case.docket_number)
                        print "                   %s" % candidates[i]['docketNumber']
                        print "      Candidate URL: %s" % (case.download_url)
                        print "      Match URL: http://courtlistener.com%s" % \
                                            (candidates[i]['absolute_url'])

                        choice = raw_input("Is this a duplicate? [y/N]: ")
                        choice = choice or "n"
                        new_stats = [stats[0], # count from search 
                                     stats[1], # count from docket number
                                     stats[2][i], # case name diff
                                     stats[3][i], # content length diff
                                     stats[4][i], # content diff
                                     choice]       # whether a dup
                        stat_file.write(','.join([str(s) for s in new_stats]) + '\n')
            else:
                print "Dup check not needed..."

            # save our location within the volume
            j += 1
            case_file = open('../logs/case_file.txt', 'w')
            case_file.write(str(j))
            case_file.close()
        # save our location within the corpus
        i += 1
        vol_file = open('../logs/vol_file.txt', 'w')
        vol_file.write(str(i))
        vol_file.close()


def train_classifier():
    '''Use the generated training data to make a logistic classifier.
    '''
    pass

def import_f3():
    '''Import F3 from resource.org using the logistic classifier.
    
    If training has not yet been run, abort.
    
    If duplicates are found, merge them and log the duplicate.
    
    If duplicates are not found, import the document.
    '''
    pass

def main():
    parser = argparse.ArgumentParser(description="Functions relating to importing "
                                                 "F3 via a logistic regression "
                                                 "classifier.")
    parser.add_argument('--gen_data',
                        action='store_true',
                        help="Generate training data as a CSV")
    parser.add_argument('--train',
                        action='store_true',
                        help="Use the generated training data to create a classifier")
    parser.add_argument('--import_f3',
                        action="store_true",
                        help=("Iterate over F3 from resource.org, and import"
                              " its contents. Use the logisitic classifier to"
                              " detect duplicates."))
    options = parser.parse_args()

    if not any([options.gen_data, options.train, options.import_f3]):
        parser.error('At least one argument is required.')

    if options.gen_data:
        generate_training_data()
    if options.train:
        train_classifier()
    if options.import_f3:
        import_f3()

    exit(0)


if __name__ == '__main__':
    main()
