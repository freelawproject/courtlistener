# -*- coding: utf-8 -*-

import re

# list of words that aren't judge names
NOT_JUDGE = [
    'above', 'absent', 'acting', 'active', 'adopted', 'affirm', 'after', 'agrees',
    'all', 'although', 'and', 'affirmed',
    'appeals', 'appellate', 'argument', 'argued', 'arj',
    'ass', 'assign', 'assigned', 'assignment', 'associate', 'assistant', 'attorney',
    'authorized', 'available', 'banc', 'bankruptcy', 'before', 'board', 'bold', 'briefs',
    'but', 'capacity', 'case', 'cause', 'center', 'certified', 'chancellor', 'chairman',
    'chief', 'circuit', 'columbia', 'commission', 'commissioner', 'composed',
    'concur', 'concurred', 'concurrence',
    'concurring', 'concurs', 'conference', 'conferences', 'considered',
    'consisted', 'consists', 'constituting', 'consultation', 'continue',
    'court', 'curiam', 'decided', 'decision', 'delivered', 'denial', 'denials', 'designation', 'did',
    'died', 'disqualified', 'dissent', 'dissented', 'dissenting', 'dissents',
    'district', 'division', 'editor', 'emeritus', 'even', 'facts', 'fellows', 'final', 'filed',
    'footnote', 'for', 'full', 'foregoing', 'four', 'furth', 'further', 'general', 'his', 'heard', 'ii', 'iii',
    'indiana', 'indicated', 'initial', 'industrial', 'issuance', 'issuing', 'italic', 'iv', 'joined', 'joins', 'judge',
    'judgement', 'judges', 'judgment', 'judicial', 'justice', 'justices', 'join',
    'magistrate', 'majority', 'making', 'maryland', 'may', 'member',
    'memorandum', 'not', 'note', 'number', 'october', 'one', 'opinion', 'oral', 'order',
    'page', 'pair', 'panel', 'part', 'participate', 'participated', 
    'participating', 'participation', 'petition', 'per', 'prepared', 'preparation', 'present',
    'president', 'presiding', 'prior',
    'pro', 'qualified', 'recusal', 'recuse', 'recused', 'reference', 'rehearing', 'report',
    'reported', 'resigned', 'reassignment', 'resident', 'resul', 'result', 'retired', 'reverse', 'reversed',
    'reservation',
    'sat', 'section', 'senior', 'separate', 'sit', 'sitting', 'special', 'specially', 'separately',
    'statement', 'states', 'stating',
    'submitted', 'surrogate', 'superior', 'supernumerary', 'taking', 'tem',
    'term', 'territorial', 'texas', 'the',
    'this', 'though', 'three', 'time', 'transfer', 'two', 
    'unanimous', 'unpublished', 'underline', 'united',
    'vacancy', 'vice', 'votes', 
    'warden', 'was', 'which', 'while', 'with', 'without', 'written',

    'january', 'february', 'march', 'april', 'june', 'july', 'august', 'september', 'october', 'november', 'december'
]

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
