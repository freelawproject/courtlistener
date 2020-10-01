


class SolrString(str):
    # The behaviour below is only really relevant for String fields rather
    # than Text fields - most queryparsers will strip these characters out
    # for a text field anyway.
    lucene_special_chars = '+-&|!(){}[]^"~*?: \t\v\\'

    def escape_for_lqs_term(self):
        if self in ["AND", "OR", "NOT", ""]:
            return '"%s"' % self
        chars = []
        for c in self.chars:
            if isinstance(c, str) and c in self.lucene_special_chars:
                chars.append("\%s" % c)
            else:
                chars.append("%s" % c)
        return "".join(chars)


class RawString(SolrString):
    def __init__(self, s):
        self.chars = self


class WildcardString(SolrString):
    def __init__(self, s):
        self.chars = self.get_wildcards(s)

    class SpecialChar(object):
        def __str__(self):
            return str(self.char)

    class Asterisk(SpecialChar):
        char = "*"

    class QuestionMark(SpecialChar):
        char = "?"

    def get_wildcards(self, s):
        backslash = False
        i = 0
        chars = []
        for c in s:
            if backslash:
                backslash = False
                chars.append(c)
                continue
            i += 1
            if c == "\\":
                backslash = True
            elif c == "*":
                chars.append(self.Asterisk())
            elif c == "?":
                chars.append(self.QuestionMark())
            else:
                chars.append(c)
        if backslash:
            chars.append("\\")
        return chars
