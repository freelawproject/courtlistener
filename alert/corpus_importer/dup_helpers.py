import os
import string
from django.utils.text import slugify
from django.utils.timezone import now

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'
import sys
execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)

from alert.lib.string_utils import anonymize, trunc
from alert.search.models import Document, save_doc_and_cite
from juriscraper.lib.string_utils import clean_string, harmonize, titlecase

import datetime
import re
import subprocess

BROWSER = 'firefox'


def merge_cases_simple(new, target_id):
    """Add `new` to the database, merging with target_id

     Merging is done by picking the best fields from each item.
    """
    target = Document.objects.get(pk=target_id)
    print "Merging %s with" % new.citation.case_name
    print "        %s" % target.citation.case_name

    if target.source == 'C':
        target.source = 'LC'
    elif target.source == 'R':
        target.source = 'LR'
    elif target.source == 'CR':
        target.source = 'LCR'

    # Recreate the slug from the new case name (this changes the URL, but the old will continue working)
    target.citation.slug = trunc(slugify(new.citation.case_name), 50)

    # Take the case name from the new item; they tend to be pretty good
    target.citation.case_name = new.citation.case_name

    # Add the docket number if the old doesn't exist, but keep the old if one does.
    if not target.citation.docket_number:
        target.citation.docket_number = new.citation.docket_number

    # Get the citations from the new item (ditch the old).
    target.citation.federal_cite_one = new.citation.federal_cite_one
    target.citation.federal_cite_two = new.citation.federal_cite_two
    target.citation.federal_cite_three = new.citation.federal_cite_three
    target.citation.state_cite_one = new.citation.state_cite_one
    target.citation.state_cite_two = new.citation.state_cite_two
    target.citation.state_cite_three = new.citation.state_cite_three
    target.citation.state_cite_regional = new.citation.state_cite_regional
    target.citation.specialty_cite_one = new.citation.specialty_cite_one
    target.citation.scotus_early_cite = new.citation.scotus_early_cite
    target.citation.lexis_cite = new.citation.lexis_cite
    target.citation.westlaw_cite = new.citation.westlaw_cite
    target.citation.neutral_cite = new.citation.neutral_cite

    # Add the URL if it's not a court one, replacing resource.org's info in some cases.
    if target.source == 'R':
        target.download_URL = new.download_URL

    # Add judge information if lacking. New is dirty, but better than none.
    if not target.judges:
        target.judges = new.judges

    # Add the text.
    target.html_lawbox, blocked = anonymize(new.html)
    if blocked:
        target.blocked = True
        target.date_blocked = now()

    target.extracted_by_ocr = False  # No longer true for any LB case.

    save_doc_and_cite(target, index=False)


def merge_cases_complex(case, target_ids):
    """Merge data from PRO with multiple cases that seem to be a match.

    The process here is a conservative one. We take *only* the information
    from PRO that is not already in CL in any form, and add only that.
    """
    for target_id in target_ids:
        simulate = False
        doc = Document.objects.get(pk=target_id)
        print "Merging %s with" % case.case_name
        print "        %s" % doc.citation.case_name

        doc.source = 'CR'
        doc.citation.west_cite = case.west_cite

        if not simulate:
            doc.citation.save()
            doc.save()


def find_same_docket_numbers(doc, candidates):
    """Identify the candidates that have the same docket numbers as doc after each has been cleaned.

    """
    new_docket_number = re.sub('(\D|0)', '', doc.citation.docket_number)
    same_docket_numbers = []
    for candidate in candidates:
        old_docket_number = re.sub('(\D|0)', '', candidate.get('docketNumber', ''))
        if all([len(new_docket_number) > 3, len(old_docket_number) > 3]):
            if old_docket_number in new_docket_number:
                same_docket_numbers.append(candidate)
    return same_docket_numbers


def case_name_in_candidate(case_name_new, case_name_candidate):
    """When there is one candidate match, this compares their case names to see if one is
    contained in the other, in the right order.

    Returns True if so, else False.
    """
    regex = re.compile('[%s]' % re.escape(string.punctuation))
    case_name_new_words = regex.sub('', case_name_new.lower()).split()
    case_name_candidate_words = regex.sub('', case_name_candidate.lower()).split()
    index = 0
    for word in case_name_new_words:
        if len(word) <= 2:
            continue
        try:
            index = case_name_candidate_words[index:].index(word)
        except ValueError:
            # The items were out of order or the item wasn't in the candidate.
            return False
    return True


def filter_by_stats(candidates, stats):
    """Looks at the candidates and their stats, and filters out obviously
    different candidates.
    """
    filtered_candidates = []
    filtered_stats = {
        'candidate_count': 0,
        'case_name_similarities': [],
        'length_diffs': [],
        'gestalt_diffs': [],
        'cos_sims': [],
    }
    for i in range(0, len(candidates)):
        # Commented out because the casenames in resource.org can be so long this varies too much.
        #if stats['case_name_similarities'][i] < 0.125:
        #    # The case name is wildly different
        #    continue
        if stats['length_diffs'][i] > 400:
            # The documents have wildly different lengths
            continue
        # Commented out because the headnotes sometimes included in Resource.org made this calculation vary too much.
        #elif stats['gestalt_diffs'][i] < 0.4:
        #    # The contents are wildly different
        #    continue
        elif stats['cos_sims'][i] < 0.85:
            # Very different cosine similarities
            continue
        else:
            # It's a reasonably close match.
            filtered_candidates.append(candidates[i])
            filtered_stats['case_name_similarities'].append(stats['case_name_similarities'][i])
            filtered_stats['length_diffs'].append(stats['length_diffs'][i])
            filtered_stats['gestalt_diffs'].append(stats['gestalt_diffs'][i])
            filtered_stats['cos_sims'].append(stats['cos_sims'][i])
    filtered_stats['candidate_count'] = len(filtered_candidates)
    return filtered_candidates, filtered_stats


class Case(object):
    def _get_case_name_and_status(self):
        case_name = self.url_element.get('title').lower()
        ca1regex = re.compile('(unpublished disposition )?notice: first circuit local rule 36.2\(b\)6 states unpublished opinions may be cited only in related cases.?')
        ca2regex = re.compile('(unpublished disposition )?notice: second circuit local rule 0.23 states unreported opinions shall not be cited or otherwise used in unrelated cases.?')
        ca2regex2 = re.compile('(unpublished disposition )?notice: this summary order may not be cited as precedential authority, but may be called to the attention of the court in a subsequent stage of this case, in a related case, or in any case for purposes of collateral estoppel or res judicata. see second circuit rule 0.23.?')
        ca3regex = re.compile('(unpublished disposition )?notice: third circuit rule 21\(i\) states citations to federal decisions which have not been formally reported should identify the court, docket number and date.?')
        ca4regex = re.compile('(unpublished disposition )?notice: fourth circuit (local rule 36\(c\)|i.o.p. 36.6) states that citation of unpublished dispositions is disfavored except for establishing res judicata, estoppel, or the law of the case and requires service of copies of cited unpublished dispositions of the fourth circuit.?')
        ca5regex = re.compile('(unpublished disposition )?notice: fifth circuit local rule 47.5.3 states that unpublished opinions should normally be cited only when they establish the law of the case, are relied upon as a basis for res judicata or collateral estoppel, or involve related facts. if an unpublished opinion is cited, a copy shall be attached to each copy of the brief.?')
        ca6regex = re.compile('(unpublished disposition )?notice: sixth circuit rule 24\(c\) states that citation of unpublished dispositions is disfavored except for establishing res judicata, estoppel, or the law of the case and requires service of copies of cited unpublished dispositions of the sixth circuit.?')
        ca7regex = re.compile('(unpublished disposition )?notice: seventh circuit rule 53\(b\)\(2\) states unpublished orders shall not be cited or used as precedent except to support a claim of res judicata, collateral estoppel or law of the case in any federal court within the circuit.?')
        ca8regex = re.compile('(unpublished disposition )?notice: eighth circuit rule 28a\(k\) governs citation of unpublished opinions and provides that (no party may cite an opinion not intended for publication unless the cases are related by identity between the parties or the causes of action|they are not precedent and generally should not be cited unless relevant to establishing the doctrines of res judicata, collateral estoppel, the law of the case, or if the opinion has persuasive value on a material issue and no published opinion would serve as well).?')
        ca9regex = re.compile('(unpublished disposition )?notice: ninth circuit rule 36-3 provides that dispositions other than opinions or orders designated for publication are not precedential and should not be cited except when relevant under the doctrines of law of the case, res judicata, or collateral estoppel.?')
        ca10regex = re.compile('(unpublished disposition )?notice: tenth circuit rule 36.3 states that unpublished opinions and orders and judgments have no precedential value and shall not be cited except for purposes of establishing the doctrines of the law of the case, res judicata, or collateral estoppel.?')
        cadcregex = re.compile('(unpublished disposition )?notice: d.c. circuit local rule 11\(c\) states that unpublished orders, judgments, and explanatory memoranda may not be cited as precedents, but counsel may refer to unpublished dispositions when the binding or preclusive effect of the disposition, rather than its quality as precedent, is relevant.?')
        cafcregex = re.compile('(unpublished disposition )?notice: federal circuit local rule 47.(6|8)\(b\) states that opinions and orders which are designated as not citable as precedent shall not be employed or cited as precedent. this does not preclude assertion of issues of claim preclusion, issue preclusion, judicial estoppel, law of the case or the like based on a decision of the court rendered in a nonprecedential opinion or order.?')
        # Clean off special cases
        if 'first circuit' in case_name:
            case_name = re.sub(ca1regex, '', case_name)
            status = 'Unpublished'
        elif 'second circuit' in case_name:
            case_name = re.sub(ca2regex, '', case_name)
            case_name = re.sub(ca2regex2, '', case_name)
            status = 'Unpublished'
        elif 'third circuit' in case_name:
            case_name = re.sub(ca3regex, '', case_name)
            status = 'Unpublished'
        elif 'fourth circuit' in case_name:
            case_name = re.sub(ca4regex, '', case_name)
            status = 'Unpublished'
        elif 'fifth circuit' in case_name:
            case_name = re.sub(ca5regex, '', case_name)
            status = 'Unpublished'
        elif 'sixth circuit' in case_name:
            case_name = re.sub(ca6regex, '', case_name)
            status = 'Unpublished'
        elif 'seventh circuit' in case_name:
            case_name = re.sub(ca7regex, '', case_name)
            status = 'Unpublished'
        elif 'eighth circuit' in case_name:
            case_name = re.sub(ca8regex, '', case_name)
            status = 'Unpublished'
        elif 'ninth circuit' in case_name:
            case_name = re.sub(ca9regex, '', case_name)
            status = 'Unpublished'
        elif 'tenth circuit' in case_name:
            case_name = re.sub(ca10regex, '', case_name)
            status = 'Unpublished'
        elif 'd.c. circuit' in case_name:
            case_name = re.sub(cadcregex, '', case_name)
            status = 'Unpublished'
        elif 'federal circuit' in case_name:
            case_name = re.sub(cafcregex, '', case_name)
            status = 'Unpublished'
        else:
            status = 'Published'

        case_name = titlecase(harmonize(clean_string(case_name)))

        if case_name == '' or case_name == 'unpublished disposition':
            # No luck getting the case name
            saved_case_name = self._check_fix_list(self.sha1_hash, self.case_name_dict)
            if saved_case_name:
                case_name = saved_case_name
            else:
                print self.url
                if BROWSER:
                    subprocess.Popen([BROWSER, self.url], shell=False).communicate()
                case_name = raw_input("Short case name: ")
                self.case_name_fix_file.write("%s|%s\n" % (self.sha1_hash, case_name))

        return case_name, status
