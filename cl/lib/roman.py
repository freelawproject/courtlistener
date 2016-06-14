import re


def isroman(s):
    """Checks if a lowercase or uppercase string is a valid Roman numeral.

    Based on: http://www.diveintopython.net/regular_expressions/n_m_syntax.html
    """
    return bool(re.search('^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$', s.upper()))