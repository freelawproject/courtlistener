# -*- coding: utf-8 -*-

import re


# list of words that aren't judge names
NOT_JUDGE = [
    'justice', 'arj', 'chief', 'prior', 'dissent', 'further', 'page', 'did', 'not', 'sit', 'conferences'
    ,'submitted', 'participate', 'participation', 'issuance', 'consultation', 'his', 'resul', 'furth', 'even'
    ,'though', 'argument', 'qualified', 'present', 'majority', 'specially', 'the', 'concurrence', 'initial'
    ,'concurring', 'final', 'may', 'dissenting', 'opinion', 'decision', 'conference', 'this', 'adopted', 'but'
    ,'retired', 'before', 'certified', 'sat', 'oral', 'resigned', 'case', 'member', 'time', 'preparation'
    ,'joined', 'active', 'while', 'order', 'participated', 'was', 'fellows', 'although', 'available'
    ,'authorized', 'continue', 'capacity', 'died', 'panel', 'sitting', 'judge', 'and', 'judges', 'senior', 'justices'
    ,'superior', 'court', 'pro', 'tem', 'participating', 'appeals', 'appellate', 'per', 'curiam', 'presiding'
    ,'supernumerary', 'circuit', 'appellate', 'part', 'division', 'vice', 'result', 'judgment', 'special', 'italic'
    ,'bold', 'denials', 'transfer', 'center', 'with', 'indiana', 'commissioner', 'dissents', 'acting', 'footnote'
    ,'reference', 'concurred', 'district', 'for', 'designation', 'cause',
    'briefs', 'considered','banc','constituting'
]

# judge names can only be this size or larger
NAME_CUTOFF = 3


def find_judges(text):
    """Returns a list of last names of judges in `text`."""
    text = text.lower() or ''
    # just use the first nonempty line (there's sometimes a useless second line)
    line = text
    if '\n' in text:
        line = ''
        for l in text.split('\n'):
            if l:
                line = l
            break
    # normalize text and get candidate judge names
    line = ''.join([c if c.isalpha() else ' ' for c in line.lower()])
    names = []
    for word in line.split():
        if len(word) < NAME_CUTOFF or word in NOT_JUDGE:
            continue
        names.append(word)
    # try to identify full judge names, and only retain their last names
    if len(names) < 2:
        last_names = names
    else:
        last_names = [names[0]]
        for i in range(len(names))[1:]:
            first_last = '%s %s' % (names[i - 1], names[i])
            first_m_last = '%s [a-z]\.? %s' % (names[i - 1], names[i])
            if re.search('%s|%s' % (first_last, first_m_last), text):
                last_names[-1] = names[i]
                continue
            last_names.append(names[i])
    return last_names


if __name__ == '__main__':
    find_judges('before: tom bryner, chief justice, tim v. matthews, eastaugh, fabe, and carpeneti, justices.')