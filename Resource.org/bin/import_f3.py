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
import re

def import_f3():
    '''Iterate over the F3 documents and import them. 
    
    A couple complications belie what would otherwise be a simple process:
     1. Duplicate detection. This is done by filtering by query and then
        refining the results that are found. For more details, see the 
        dup_finder code. 
     2. Merging duplicate documents. See their code in the f3_helpers module.
    '''
    simulate = False
    corpus = f3_helpers.Corpus('file:///var/www/court-listener/Resource.org/data/F3/')
    vol_file = open('../logs/vol_file.txt', 'r+')
    case_file = open('../logs/case_file.txt', 'r+')
    stat_file = open('../logs/training_stats.csv', 'a')
    try:
        volume_num = int(vol_file.readline())
    except ValueError:
        # the volume file is emtpy or otherwise failing.
        volume_num = 0
    vol_file.close()
    for volume in corpus[volume_num:]:
        print "################"
        print " Vol: %s" % volume_num
        print "################"
        try:
            j = int(case_file.readline())
            print "Case: %s" % j
        except ValueError:
            j = 0
        case_file.close()
        for case in volume[j:]:
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
                    print "  No candidates found. Adding the opinion."
                    if not simulate:
                        f3_helpers.add_case(case)
                elif (re.sub("(\D|0)", "", case.docket_number) == \
                            re.sub("(\D|0)", "", candidates[0]['docketNumber'])) and \
                            (len(candidates) == 1):
                    # If the docket numbers are identical, and there was only 
                    # one result
                    print "  Match made on docket number of single candidate. Merging the opinions."
                    if not simulate:
                        f3_helpers.merge_cases_simple(case, candidates[0]['id'])
                elif len(f3_helpers.find_same_docket_numbers(case, candidates)) == 1:
                    print "  One of the %s candidates had an identical docket number. Merging the opinions." % len(candidates)
                    if not simulate:
                        f3_helpers.merge_cases_simple(case, f3_helpers.find_same_docket_numbers(case, candidates)[0]['id'])
                elif len(f3_helpers.find_same_docket_numbers(case, candidates)) > 0:
                    print "  Several of the %s candidates had an identical docket number. Merging the opinions." % len(candidates)
                    if not simulate:
                        target_ids = [candidate['id'] for candidate in f3_helpers.find_same_docket_numbers(case, candidates)]
                        f3_helpers.merge_cases_complex(case, target_ids)
                else:
                    # Possible duplicate, filter out obviously bad cases, and 
                    # then pass forward for manual review if necessary.
                    filtered_candidates, stats = f3_helpers.filter_by_stats(candidates, stats)
                    if len(filtered_candidates) == 0:
                        print "After filtering, no candidates remain. Adding the opinion."
                        if not simulate:
                            f3_helpers.add_case(case)
                    else:
                        print "Needs determination by hand. Adding to hand file."
                        possible_ids = [can['id'] for can in filtered_candidates]
                        hand_file = open('../logs/hand_file.csv', 'a')
                        hand_file.write(str(volume_num) + ',' + str(j) + '\n')
                        hand_file.close()
            else:
                print "Dup check not needed. Adding the opinion."
                if not simulate:
                    f3_helpers.add_case(case)

            # save our location within the volume
            j += 1
            case_file = open('../logs/case_file.txt', 'w')
            case_file.write(str(j))
            case_file.close()
        # save our location within the corpus
        volume_num += 1
        vol_file = open('../logs/vol_file.txt', 'w')
        vol_file.write(str(volume_num))
        vol_file.close()

def main():
    import_f3()
    exit(0)

if __name__ == '__main__':
    main()
