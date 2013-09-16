from juriscraper.lib.string_utils import titlecase
import re
import string


REASONS = {
    0: 'TOO_SHORT',
    1: 'TOO_LONG',
    2: 'STARTS_WITH_NON_ASCII',
    3: 'BAD_FIRST_WORD',
    4: 'BAD_WORD_FOUND',
    5: 'MATCH_ON_REGEX_DELIVERED',
    6: 'PER_CURIAM',
    7: 'UPPERCASE_AND_JUDICIARY_WORD',
    8: 'STARTS_WITH_OPINION_BY',
    9: 'NO_MATCH_FOUND',
    10: 'STARTS_WITH_LOWERCASE_AND_ENDS_WITH_NON_JUDICIARY_WORD',
    11: 'MATCH_ON_REGEX_DELIVERED_BY',
    12: 'MATCH_ON_REGEX_ORDER_OF',
    14: 'STARTS_WITH_BEFORE',
    15: 'STARTS_WITH_CHIEF_JUDGE',
    16: 'MEMORANDUM_CONCURRENCE',
    17: 'MATCH_ON_REGEX_ARGUED_BEFORE',
    18: 'STARTS_WITH_LOWERCASE_THE',
}


def get_judge_from_str(t):
    """Returns the judge's name if the string looks like a judge. Else, returns False"""
    judge = False

    # From Blue Book, T11, plus a review of about 100,000 found "judges"
    judiciary_synonyms = ('curiam', 'judge', 'consultant', 'justice', 'referee', 'magistrate', 'j.', 'a.l.j.', 'arb.',
                          'c.b.', 'hon.', 'jj.', 'p.j.', 'p. j.', 'c.')
    bad_words = ('plaintiff', 'defendant', 'order', 'concluding', 'considering', 'accepting', 'addressing', 'admitting',
                 'curiae', 'appellant', 'discussing', 'examining', '(^| )going', 'granting', 'arguments?', 'denying',
                 'findings', 'proceeding', 'turning')
    bad_words_regex = re.compile('(%s)' % ')|('.join(bad_words), re.I)
    bad_starting_words = ('amended ', 'decision ', 'memorandum ', 'trial ', '"', '\(', '[0-9]', ':', '>', '\[', 'a ',
                          '\{', '\}', 'any ', 'that ', 'there ', 'this ', 'u\.s\.', 'us ', 'we ', 'an ', 'and ', 'tex',
                          'krs', 'his ', 'her ', 'I ', 'II ', 'III ', 'IV ', 'V ', 'in ', 'it ', 'llp', 'llc', 'on ',
                          'present', 'argued')
    # Beginning of line followed by any of the stuff above, case insensitive
    bad_starting_words_regex = re.compile('^(%s)' % '|'.join(bad_starting_words), re.I)

    # Carefully uppercase things like 'Mc'
    prefixes = ('Mc', 'Te', 'Mac', 'Di', 'De', 'Van', 'Le')
    for prefix in prefixes:
        if prefix in t:
            t = t.replace(prefix, prefix.upper())

    words = t.split(' ')

    # Early abortion opportunities
    if len(words) > 100:
        # We're past the headnotes and into the paragraphs. Bail.
        return False, REASONS[1]
    if len(t) == 0:
        return False, REASONS[0]

    if t.lower().startswith('opinion by'):
        t = t.replace('OPINION BY ', '')
        judge = titlecase(' '.join([word for word in t.split(' ') if word.isupper()]))
        reason = REASONS[8]
    elif re.search('((delivered)|(announced)) the ((opinion)|(judge?ment))', t, re.I):
        regexes = (
            '(.*), J\.,?.*((?:delivered)|(?:announced)) the ((?:judgment)|(?:opinion)) of the court',
            'justice (.*) delivered the (?:(?:judge?ment)|(?:opinion)) of the court',
        )
        for regex in regexes:
            try:
                match = re.search(regex, t, re.I)
                judge = titlecase(match.group(1).upper())
                reason = REASONS[5]
            except AttributeError:
                continue
    elif 'opinion of the court was delivered by' in t.lower():
        match = re.search('opinion of the court was delivered by (.*)', t, re.I)
        try:
            judge = titlecase(match.group(1).upper())
            reason = REASONS[11]
        except AttributeError:
            pass
    elif 'the following is the order of judge' in t.lower():
        match = re.search('the following is the order of judge (.*)', t, re.I)
        try:
            judge = titlecase(match.group(1).upper())
            reason = REASONS[12]
        except AttributeError:
            pass
    elif t.lower().startswith('chief judge '):
        judge = titlecase(t.upper()).split('Chief Judge ')[1]
        reason = REASONS[15]
    elif t.lower().startswith('before') and not re.search(bad_words_regex, t):
        try:
            judge = titlecase(t.upper()).split(' ', 1)[1]
            reason = REASONS[14]
        except IndexError:
            pass
    elif 'argued before' in t.lower():
        match = re.search('argued before (.*)', t, re.I)
        try:
            judge = titlecase(match.group(1).upper())
            reason = REASONS[17]
        except AttributeError:
            pass
    elif 'concur in memorandum' in t.lower():
        judge = titlecase(t.upper())
        reason = REASONS[16]
    else:
        # So far, so good, try looking for uppercase words that we like
        long_words = [word for word in words if len(word) > 2 and
                                                '.' not in word.strip(string.punctuation) and
                                                word.strip(string.punctuation).isalpha() and
                                                word.lower() != 'van' '']

        # Opportunities for early abortion. If it makes it past here, it's a winner.
        try:
            if not long_words[0].isupper():
                if [j for j in judiciary_synonyms if t.lower().strip(',. ').endswith(' ' + j.strip('.'))]:
                    # One last chance -- does it end with a judiciary_synonym?
                    pass
                else:
                    return False, REASONS[10]
        except IndexError:
            # The length of the string is too short.
            return False, REASONS[0]

        if [_ for _ in judiciary_synonyms if _ in t.lower()] and not re.search(bad_words_regex, t):
            if 'curiam' in t.lower():
                judge = 'Per Curiam'
                reason = REASONS[6]
            else:
                try:
                    # Split on comma, and off we go
                    judge, suffix = t.split(',', 1)
                    if suffix.strip(' ,.').lower().startswith('jr.'):
                        judge += ', JR.'  # Uppercase so titlecase properly gets triggered
                except ValueError:
                    judge = ' '.join([word for word in t.split() if word.isupper()])
                judge = titlecase(judge.upper())
                reason = REASONS[7]

    # Late abortion opportunities. Uses early termination of conditionals to bail if judge == False.
    if judge and ord(judge[0]) > 127:
        # Unicode madness
        return False, REASONS[2]
    if judge and (t.startswith('the ') or judge.startswith('the ')):
        return False, REASONS[18]
    if judge and re.search(bad_starting_words_regex, judge):
        # Bad first word/characters
        return False, REASONS[3]
    if re.search(bad_words_regex, t):
        # Bad word found. Abort
        if 'the following is the order of judge' in t.lower():
            pass
        else:
            return False, REASONS[4]
    if judge and len(judge) == 0:
        return False, REASONS[0]

    if judge:
        # Cleanup
        if not judge.endswith('Jr.'):
            judge = judge.strip('.,; ')

        if judge.endswith('JJ'):
            judge = judge.split('JJ', 1)[0]
        elif judge.endswith('J'):
            judge = judge.split('J', 1)[0]

        if not judge.endswith('Jr.'):
            judge = judge.strip('., ')

        return judge, reason
    else:
        return False, REASONS[9]
