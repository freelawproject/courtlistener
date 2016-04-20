# -*- coding: utf-8 -*-

import re

# list of words that aren't judge names
NOT_JUDGE = {
    'acting', 'active', 'adopted', 'although', 'and', 'appeals', 'appellate',
    'argument', 'arj', 'associate', 'authorized', 'available', 'banc', 'before',
    'bold', 'briefs', 'but', 'capacity', 'case', 'cause', 'center', 'certified',
    'chief', 'circuit', 'commissioner', 'concurred', 'concurrence',
    'concurring', 'conference', 'conferences', 'considered', 'constituting',
    'consultation', 'continue', 'court', 'curiam', 'decision', 'denials',
    'designation', 'did', 'died', 'dissent', 'dissenting', 'dissents',
    'district', 'division', 'even', 'fellows', 'final', 'footnote', 'for',
    'furth', 'further', 'his', 'indiana', 'initial', 'issuance', 'italic',
    'joined', 'judge', 'judges', 'judgment', 'judgement', 'justice', 'justices',
    'majority', 'may', 'member', 'not', 'number', 'opinion', 'oral', 'order',
    'page', 'panel', 'part', 'participate', 'participated', 'participating',
    'participation', 'per', 'preparation', 'present', 'presiding', 'prior',
    'pro', 'qualified', 'reference', 'resigned', 'resul', 'result', 'retired',
    'sat', 'senior', 'sit', 'sitting', 'special', 'specially', 'submitted',
    'superior', 'supernumerary', 'tem', 'the', 'this', 'though', 'time',
    'transfer', 'vice', 'was', 'while', 'with',
}

# judge names can only be this size or larger
NAME_CUTOFF = 3

# for judges with small names, need an override
IS_JUDGE = {'wu', 're', 'du'}

def find_judges(text, first_names=False):
    """Returns a list of last names of judges in `text`.

    :param first_names: If True, will return a list of `(first, last)` tuples, in which `first` will usually be None
    unless a judge's first name is identified.
    """
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
        if (len(word) < NAME_CUTOFF and word not in IS_JUDGE) or word in NOT_JUDGE:
            continue
        names.append(word)
    # try to identify which names are first and last names
    if len(names) < 2:
        last_names = names
        first_last_names = [(None, l) for l in last_names]
    else:
        last_names = [names[0]]
        first_last_names = [(None, names[0])]
        for i in range(len(names))[1:]:
            first_last = '%s %s' % (names[i - 1], names[i])
            first_m_last = '%s [a-z]\.? %s' % (names[i - 1], names[i])
            if re.search('%s|%s' % (first_last, first_m_last), text):
                first_last_names[-1] = (first_last_names[-1][1], names[i])
                last_names[-1] = names[i]
                continue
            first_last_names.append((None, names[i]))
            last_names.append(names[i])
    return first_last_names if first_names else last_names


def judges_exist(text, judges):
    """Checks whether any of `judges` are in `text`. Returns the elements in `judges` that are matched.

    :param text: String.
    :param judges: Either a list of last names or a list of `(first, last)` tuples of judge names. These types can be
    mixed, e.g. in a list ['last1', ('first2', 'last2'), 'last3'].
    """
    matched = []
    for judge in judges:
        if isinstance(judge, basestring):
            if re.search(r'\b%s\b' % judge, text):
                matched.append(judge)
            continue
        first_last = '%s %s' % judge
        first_m_last = '%s [a-z]\.? %s' % judge
        if re.search(r'\b(%s|%s)\b' % (first_last, first_m_last), text):
            matched.append(judge)
    return matched


if __name__ == '__main__':
    s = 'before: tom bryner, chief justice, tim v. matthews, eastaugh, fabe, and carpeneti, justices.'
    print judges_exist(s, ['bryner', ('tim', 'matthews')])
