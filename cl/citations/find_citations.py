#!/usr/bin/env python
# encoding: utf-8
import re
import sys

from juriscraper.lib.html_utils import get_visible_text
from reporters_db import EDITIONS, REPORTERS, VARIATIONS_ONLY
from django.utils.timezone import now
from cl.citations import reporter_tokenizer
from cl.search.models import Court


FORWARD_SEEK = 20

BACKWARD_SEEK = 28  # Median case name length in the db is 28 (2016-02-26)

STOP_TOKENS = ['v', 're', 'parte', 'denied', 'citing', "aff'd", "affirmed",
               "remanded", "see", "granted", "dismissed"]

# Store court values to avoid repeated DB queries
if not set(sys.argv).isdisjoint(['test', 'syncdb', 'shell', 'migrate']):
    # If it's a test, we can't count on the database being prepped, so we have
    # to load lazily
    ALL_COURTS = Court.objects.all().values('citation_string', 'pk')
else:
    # list() forces early evaluation of the queryset so we don't have issues
    # with closed cursors.
    ALL_COURTS = list(Court.objects.all().values('citation_string', 'pk'))


class Citation(object):
    """Convenience class which represents a single citation found in a
    document.
    """
    def __init__(self, reporter, page, volume, canonical_reporter=None,
                 lookup_index=None, extra=None, defendant=None, plaintiff=None,
                 court=None, year=None, match_url=None, match_id=None,
                 reporter_found=None, reporter_index=None):

        # Core data.
        self.reporter = reporter
        self.volume = volume
        self.page = page

        # These values are set during disambiguation.
        self.canonical_reporter = canonical_reporter
        self.lookup_index = lookup_index

        # Supplementary data, if possible.
        self.extra = extra
        self.defendant = defendant
        self.plaintiff = plaintiff
        self.court = court
        self.year = year

        # The reporter found in the text is often different from the reporter
        # once it's normalized. We need to keep the original value so we can
        # linkify it with a regex.
        self.reporter_found = reporter_found

        # The location of the reporter is useful for tasks like finding parallel
        # citations, and finding supplementary info like defendants and years.
        self.reporter_index = reporter_index

        # Attributes of the matching item, for URL generation.
        self.match_url = match_url
        self.match_id = match_id

        self.equality_attributes = [
            'reporter', 'volume', 'page', 'canonical_reporter', 'lookup_index',
        ]

    def base_citation(self):
        return u"%d %s %d" % (self.volume, self.reporter, self.page)

    def as_regex(self):
        return r"%d(\s+)%s(\s+)%d" % (
            self.volume,
            re.escape(self.reporter_found),
            self.page
        )

    # TODO: Update css for no-link citations
    def as_html(self):
        # Uses reporter_found so that we don't update the text. This guards us
        # against accidentally updating things like docket number 22 Cr. 1 as
        # 22 Cranch 1, which is totally wrong.
        template = u'<span class="volume">%(volume)d</span>\\1' \
                   u'<span class="reporter">%(reporter_found)s</span>\\2' \
                   u'<span class="page">%(page)d</span>'
        inner_html = template % self.__dict__
        span_class = "citation"
        if self.match_url:
            inner_html = u'<a href="%s">%s</a>' % (self.match_url, inner_html)
            data_attr = u' data-id="%s"' % self.match_id
        else:
            span_class += " no-link"
            data_attr = ''
        return u'<span class="%s"%s>%s</span>' % \
               (span_class, data_attr, inner_html)

    def __repr__(self):
        print_string = self.base_citation()
        if self.defendant:
            print_string = u' '.join([self.defendant, print_string])
            if self.plaintiff:
                print_string = u' '.join([self.plaintiff, 'v.', print_string])
        if self.extra:
            print_string = u' '.join([print_string, self.extra])
        if self.court and self.year:
            paren = u"(%s %d)" % (self.court, self.year)
        elif self.year:
            paren = u'(%d)' % self.year
        elif self.court:
            paren = u"(%s)" % self.court
        else:
            paren = ''
        print_string = u' '.join([print_string, paren])
        return print_string.encode("utf-8")

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self.__eq__(other)

    def fuzzy_hash(self):
        """Used to test equality in dicts.

        Overridden here to simplify away some of the attributes that can differ
        for the same citation.
        """
        s = ''
        for attr in self.equality_attributes:
            s += str(getattr(self, attr, None))
        return hash(s)

    def fuzzy_eq(self, other):
        """Used to override the __eq__ function."""
        return self.fuzzy_hash() == other.fuzzy_hash()


# Adapted from nltk Penn Treebank tokenizer
def strip_punct(text):
    #starting quotes
    text = re.sub(r'^\"', r'', text)
    text = re.sub(r'(``)', r'', text)
    text = re.sub(r'([ (\[{<])"', r'', text)

    #punctuation
    text = re.sub(r'\.\.\.', r'', text)
    text = re.sub(r'[,;:@#$%&]', r'', text)
    text = re.sub(r'([^\.])(\.)([\]\)}>"\']*)\s*$', r'\1', text)
    text = re.sub(r'[?!]', r'', text)

    text = re.sub(r"([^'])' ", r"", text)

    #parens, brackets, etc.
    text = re.sub(r'[\]\[\(\)\{\}\<\>]', r'', text)
    text = re.sub(r'--', r'', text)

    #ending quotes
    text = re.sub(r'"', "", text)
    text = re.sub(r'(\S)(\'\')', r'', text)

    return text.strip()


def is_scotus_reporter(citation):
    try:
        reporter = REPORTERS[citation.canonical_reporter][citation.lookup_index]
    except (TypeError, KeyError):
        # Occurs when citation.lookup_index is None
        return False

    if reporter:
        truisms = [
            (reporter['cite_type'] == 'federal' and
             'supreme' in reporter['name'].lower()),
            'scotus' in reporter['cite_type'].lower()
        ]
        if any(truisms):
            return True
    else:
        return False


def get_court_by_paren(paren_string, citation):
    """Takes the citation string, usually something like "2d Cir", and maps
    that back to the court code.

    Does not work on SCOTUS, since that court lacks parentheticals, and needs to
    be handled after disambiguation has been completed.
    """
    if citation.year is None:
        court_str = strip_punct(paren_string)
    else:
        year_index = paren_string.find(str(citation.year))
        court_str = strip_punct(paren_string[:year_index])

    court_code = None
    if court_str == u'':
        court_code = None
    else:
        # Map the string to a court, if possible.
        for court in ALL_COURTS:
            # Use startswith because citations are often missing final period,
            # e.g. "2d Cir"
            if court['citation_string'].startswith(court_str):
                court_code = court['pk']
                break

    return court_code


def get_year(token):
    """Given a string token, look for a valid 4-digit number at the start and
    return its value.
    """
    token = strip_punct(token)
    if not token.isdigit():
        # Sometimes funny stuff happens?
        token = re.sub(r'(\d{4}).*', r'\1', token)
        if not token.isdigit():
            return None
    if len(token) != 4:
        return None
    year = int(token)
    if year < 1754:  # Earliest case in the database
        return None
    return year


def add_post_citation(citation, words):
    """Add to a citation object any additional information found after the base
    citation, including court, year, and possibly page range.

    Examples:
        Full citation: 123 U.S. 345 (1894)
        Post-citation info: year=1894

        Full citation: 123 F.2d 345, 347-348 (4th Cir. 1990)
        Post-citation info: year=1990, court="4th Cir.", extra (page range)="347-348"
    """
    # Start looking 2 tokens after the reporter (1 after page), and go to
    # either the end of the words list or to FORWARD_SEEK tokens from where you
    # started.
    for start in xrange(
            citation.reporter_index + 2,
            min((citation.reporter_index + FORWARD_SEEK), len(words))):
        if words[start].startswith('('):
            # Get the year by looking for a token that ends in a paren.
            for end in xrange(start, start + FORWARD_SEEK):
                try:
                    has_ending_paren = (words[end].find(')') > -1)
                except IndexError:
                    # Happens with words like "(1982"
                    break
                if has_ending_paren:
                    # Sometimes the paren gets split from the preceding content
                    if words[end].startswith(')'):
                        citation.year = get_year(words[end - 1])
                    else:
                        citation.year = get_year(words[end])
                    citation.court = get_court_by_paren(u' '.join(words[start:end + 1]), citation)
                    break

            if start > citation.reporter_index + 2:
                # Then there's content between page and (), starting with a
                # comma, which we skip
                citation.extra = u' '.join(
                        words[citation.reporter_index + 2:start])
            break


def add_defendant(citation, words):
    """Scan backwards from 2 tokens before reporter until you find v., in re,
    etc. If no known stop-token is found, no defendant name is stored.  In the
    future, this could be improved.
    """
    start_index = None
    for index in xrange(
            citation.reporter_index - 1,
            max(citation.reporter_index - BACKWARD_SEEK, 0), -1):
        word = words[index]
        if word == ',':
            # Skip it
            continue
        if strip_punct(word).lower() in STOP_TOKENS:
            if word == 'v.':
                citation.plaintiff = words[index - 1]
            start_index = index + 1
            break
        if word.endswith(';'):
            # String citation
            break
    if start_index:
        citation.defendant = u' '.join(
                words[start_index:citation.reporter_index - 1])


def extract_base_citation(words, reporter_index):
    """Construct and return a citation object from a list of "words"

    Given a list of words and the index of a federal reporter, look before and
    after for volume and page number.  If found, construct and return a
    Citation object.
    """
    volume = strip_punct(words[reporter_index - 1])
    if volume.isdigit():
        volume = int(volume)
    else:
        # No volume, therefore not a valid citation
        return None

    page = strip_punct(words[reporter_index + 1])
    if page.isdigit():
        page = int(page)
    else:
        # No page, therefore not a valid citation
        return None

    reporter = words[reporter_index]
    return Citation(reporter, page, volume, reporter_found=reporter,
                    reporter_index=reporter_index)


def is_date_in_reporter(editions, year):
    """Checks whether a year falls within the range of 1 to n editions of a
    reporter

    Editions will look something like:
        'editions': {'S.E.': {'start': datetime.datetime(1887, 1, 1),
                              'end': datetime.datetime(1939, 12, 31)},
                     'S.E.2d': {'start': datetime.datetime(1939, 1, 1),
                                'end': None}},
    """
    for date_dict in editions.values():
        if date_dict['end'] is None:
            date_dict['end'] = now()
        if date_dict['start'].year <= year <= date_dict['end'].year:
            return True
    return False


def disambiguate_reporters(citations):
    """Convert a list of citations to a list of unambiguous ones.

    Goal is to figure out:
     - citation.canonical_reporter
     - citation.lookup_index

    And there are a few things that can be ambiguous:
     - More than one variation.
     - More than one reporter for the key.
     - Could be an edition (or not)
     - All combinations of the above:
        - More than one variation.
        - More than one variation, with more than one reporter for the key.
        - More than one variation, with more than one reporter for the key,
          which is an edition.
        - More than one variation, which is an edition
        - ...

    For variants, we just need to sort out the canonical_reporter.

    If it's not possible to disambiguate the reporter, we simply have to drop
    it.
    """
    unambiguous_citations = []
    for citation in citations:
        # Non-variant items (P.R.R., A.2d, Wash., etc.)
        if REPORTERS.get(EDITIONS.get(citation.reporter)) is not None:
            citation.canonical_reporter = EDITIONS[citation.reporter]
            if len(REPORTERS[EDITIONS[citation.reporter]]) == 1:
                # Single reporter, easy-peasy.
                citation.lookup_index = 0
                unambiguous_citations.append(citation)
                continue
            else:
                # Multiple books under this key, but which is correct?
                if citation.year:
                    # attempt resolution by date
                    possible_citations = []
                    for i in range(0, len(REPORTERS[EDITIONS[citation.reporter]])):
                        if is_date_in_reporter(REPORTERS[EDITIONS[citation.reporter]][i]['editions'], citation.year):
                            possible_citations.append((citation.reporter, i,))
                    if len(possible_citations) == 1:
                        # We were able to identify only one hit after filtering
                        # by year.
                        citation.reporter = possible_citations[0][0]
                        citation.lookup_index = possible_citations[0][1]
                        unambiguous_citations.append(citation)
                        continue

        # Try doing a variation of an edition.
        elif VARIATIONS_ONLY.get(citation.reporter) is not None:
            if len(VARIATIONS_ONLY[citation.reporter]) == 1:
                # Only one variation -- great, use it.
                citation.canonical_reporter = EDITIONS[VARIATIONS_ONLY[citation.reporter][0]]
                cached_variation = citation.reporter
                citation.reporter = VARIATIONS_ONLY[citation.reporter][0]
                if len(REPORTERS[citation.canonical_reporter]) == 1:
                    # It's a single reporter under a misspelled key.
                    citation.lookup_index = 0
                    unambiguous_citations.append(citation)
                    continue
                else:
                    # Multiple reporters under a single misspelled key
                    # (e.g. Wn.2d --> Wash --> Va Reports, Wash or
                    #                          Washington Reports).
                    if citation.year:
                        # attempt resolution by date
                        possible_citations = []
                        for i in range(0, len(REPORTERS[citation.canonical_reporter])):
                            if is_date_in_reporter(REPORTERS[citation.canonical_reporter][i]['editions'],
                                                   citation.year):
                                possible_citations.append((citation.reporter, i))
                        if len(possible_citations) == 1:
                            # We were able to identify only one hit after
                            # filtering by year.
                            citation.lookup_index = possible_citations[0][1]
                            unambiguous_citations.append(citation)
                            continue
                    # Attempt resolution by unique variation (e.g. Cr. can only
                    # be Cranch[0])
                    possible_citations = []
                    for i in range(0, len(REPORTERS[citation.canonical_reporter])):
                        for variation in REPORTERS[citation.canonical_reporter][i]['variations'].items():
                            if variation[0] == cached_variation:
                                possible_citations.append((variation[1], i))
                    if len(possible_citations) == 1:
                        # We were able to find a single match after filtering
                        # by variation.
                        citation.lookup_index = possible_citations[0][1]
                        unambiguous_citations.append(citation)
                        continue
            else:
                # Multiple variations, deal with them.
                possible_citations = []
                for reporter_key in VARIATIONS_ONLY[citation.reporter]:
                    for i in range(0, len(REPORTERS[EDITIONS[reporter_key]])):
                        # This inner loop works regardless of the number of
                        # reporters under the key.
                        if is_date_in_reporter(REPORTERS[EDITIONS[reporter_key]][i]['editions'], citation.year):
                            possible_citations.append((reporter_key, i,))
                if len(possible_citations) == 1:
                    # We were able to identify only one hit after filtering by
                    # year.
                    citation.canonical_reporter = EDITIONS[possible_citations[0][0]]
                    citation.reporter = possible_citations[0][0]
                    citation.lookup_index = possible_citations[0][1]
                    unambiguous_citations.append(citation)
                    continue

    return unambiguous_citations


def get_citations(text, html=True, do_post_citation=True, do_defendant=True):
    if html:
        text = get_visible_text(text)
    words = reporter_tokenizer.tokenize(text)
    citations = []
    # Exclude first and last tokens when looking for reporters, because valid
    # citations must have a volume before and a page number after the reporter.
    for i in xrange(1, len(words) - 1):
        # Find reporter
        if words[i] in (EDITIONS.keys() + VARIATIONS_ONLY.keys()):
            citation = extract_base_citation(words, i)
            if citation is None:
                # Not a valid citation; continue looking
                continue
            if do_post_citation:
                add_post_citation(citation, words)
            if do_defendant:
                add_defendant(citation, words)
            citations.append(citation)

    # Disambiguate or drop all the reporters
    citations = disambiguate_reporters(citations)

    for citation in citations:
        if not citation.court and is_scotus_reporter(citation):
            citation.court = 'scotus'

    return citations
