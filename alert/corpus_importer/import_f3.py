import dup_finder
import f3_helpers
import re
import sys


def run_dup_check(case, simulate=True):
    """Runs a series of duplicate checking code, generating and analyzing
    stats about whether the case is a duplicate.

    """
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
            target_ids = [can['id'] for can in f3_helpers.find_same_docket_numbers(case, candidates)]
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
            print "FILTERED STATS: %s" % stats
            duplicates = []
            for k in range(0, len(filtered_candidates)):
                # Have to determine by "hand"
                print "  %s) Case name: %s" % (k + 1, case.case_name)
                print "                %s" % filtered_candidates[k]['caseName']
                print "      Docket nums: %s" % (case.docket_number)
                print "                   %s" % filtered_candidates[k]['docketNumber']
                print "      Candidate URL: %s" % (case.download_url)
                print "      Match URL: http://courtlistener.com%s" % \
                                      (filtered_candidates[k]['absolute_url'])

                choice = raw_input("Is this a duplicate? [Y/n]: ")
                choice = choice or "y"
                if choice == 'y':
                    duplicates.append(filtered_candidates[k]['id'])

            if len(duplicates) == 0:
                print "No duplicates found after manual determination. Adding the opinion."
                if not simulate:
                    f3_helpers.add_case(case)
            elif len(duplicates) == 1:
                print "Single duplicate found after manual determination. Merging the opinions."
                if not simulate:
                    f3_helpers.merge_cases_simple(case, duplicates[0])
            elif len(duplicates) > 1:
                print "Multiple duplicates found after manual determination. Merging the opinions."
                if not simulate:
                    f3_helpers.merge_cases_complex(case, duplicates)


def import_by_hand():
    """Iterates over the hand_file list, and presents them to a human for
    resolution

    The automated importer was unable to resolve all cases, and made a list of
    the ones it could not handle. This function takes that list, and iterates
    over it so that the documents can be imported manually.
    """
    simulate = False
    corpus = f3_helpers.Corpus('file:///var/www/court-listener/Resource.org/data/F3/')
    hand_file = open('/var/www/court-listener/Resource.org/logs/hand_file.csv', 'r')
    line_placeholder = open('/var/www/court-listener/Resource.org/logs/line_placeholder.txt', 'r+')
    try:
        line_num_done = int(line_placeholder.readline())
    except ValueError:
        # the volume file is empty or otherwise failing.
        line_num_done = 0
    line_placeholder.close()
    for line in hand_file.readlines()[line_num_done:]:
        vol_num, case_num = [int(line.strip()) for line in line.split(',')]
        # There was an off-by-one error when the hand_file was created.
        vol_num += 1
        print "\nVol: %s -- Case: %s" % (vol_num, case_num)
        volume = corpus[int(vol_num)]
        print "Volume of %s cases is at: %s" % (len(volume), volume.url)
        case = volume[int(case_num)]
        run_dup_check(case, simulate)
        line_num_done += 1
        line_placeholder = open('/var/www/court-listener/Resource.org/logs/line_placeholder.txt', 'w')
        line_placeholder.write(str(line_num_done))
        line_placeholder.close()


def import_f3():
    """Iterate over the F3 documents and import them.

    A couple complications belie what would otherwise be a simple process:
     1. Duplicate detection. This is done by filtering by query and then
        refining the results that are found. For more details, see the
        dup_finder code.
     2. Merging duplicate documents. See their code in the f3_helpers module.
    """
    simulate = False
    corpus = f3_helpers.Corpus('/var/www/court-listener/Resource.org/data/F3/')
    vol_file = open('/var/www/court-listener/Resource.org/logs/vol_file.txt', 'r+')
    case_file = open('/var/www/court-listener/Resource.org/logs/case_file.txt', 'r+')
    stat_file = open('/var/www/court-listener/Resource.org/logs/training_stats.csv', 'a')
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
                run_dup_check(case, simulate)
            else:
                print "Dup check not needed. Adding the opinion."
                if not simulate:
                    f3_helpers.add_case(case)

            # save our location within the volume
            j += 1
            case_file = open('/var/www/court-listener/Resource.org/logs/case_file.txt', 'w')
            case_file.write(str(j))
            case_file.close()
        # save our location within the corpus
        volume_num += 1
        vol_file = open('/var/www/court-listener/Resource.org/logs/vol_file.txt', 'w')
        vol_file.write(str(volume_num))
        vol_file.close()

def main():
    if len(sys.argv) != 2:
        sys.exit("Wrong number of arguments. Usage: python import_f3.py (--import | --hand)")
    elif sys.argv[1] == '--import':
        import_f3()
    elif sys.argv[1] == '--hand':
        import_by_hand()
    else:
        sys.exit("Usage: python import_f3.py (--import | --hand)")
    exit(0)

if __name__ == '__main__':
    main()
