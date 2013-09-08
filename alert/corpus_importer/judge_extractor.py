from juriscraper.lib.string_utils import titlecase


def get_judge_from_str(t, forward_test=2):
    """Returns the judge's name if the string looks like a judge. Else, returns False"""
    judge = False
    if len(t) < 2:
        return judge

    # Carefully uppercase things like 'Mc'
    if 'Mc' in t:
        t = t.replace('Mc', 'MC')

    words = t.split(' ')

    # Tests foward_test number of words to make sure they are uppercase. The
    # caller should start with a high count, then decrement it until a hit
    # is found.
    for i in range(forward_test - 1):
        if not words[i].isupper():
            return judge

    # A couple sanity checks
    judiciary_synonyms = ('judge', 'consultant', 'justice')

    if [j for j in judiciary_synonyms if j in t.lower()]:
        # Split on comma, and off we go
        judge = titlecase(t.split(',')[0])
        if 'Jr.' in t:
            judge += ', Jr.'
    return judge
