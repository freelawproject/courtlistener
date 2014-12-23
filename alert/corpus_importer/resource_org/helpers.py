from juriscraper.lib.string_utils import titlecase, harmonize, clean_string
import re
import datetime
from lxml.html import tostring


def get_case_name_and_status(vol_tree, case_location):
    case_name_node = vol_tree.xpath('//a[@href="%s"]' % case_location)
    case_name_dirty = case_name_node.get('title')
    return get_clean_case_name_and_sniff_status(case_name_dirty)


def get_date_filed(vol_tree, case_location):
    d_node = vol_tree.xpath('//a[@href="%s"]' % case_location)
    d_str = d_node.text.strip()
    return datetime.datetime.strptime(d_str, '%B %d, %Y')


def get_docket_number(case_location):
    return case_location.split('.')[-2]

def get_west_cite(vol_tree, case_location):
    return vol_tree.xpath('//a[@href="%s"][1]/text()' % case_location)

def get_clean_case_name_and_sniff_status(s):
    """Strips out warnings re non-precedential status that occur in case
    names. If such a warning is discovered, we set the status flag to
    'nonprecedential'.

    Returns a cleaned case name and the status of the item, both as
    strings.
    """
    s = s.lower()
    regexes = (
        ('first circuit',
         '(unpublished disposition )?notice: first circuit local rule 36.2'
         '\(b\)6 states unpublished opinions may be cited only in related '
         'cases.?'),
        ('second circuit',
         '(unpublished disposition )?notice: second circuit local rule '
         '0.23 states unreported opinions shall not be cited or otherwise '
         'used in unrelated cases.?'),
        ('second circuit',
         '(unpublished disposition )?notice: this summary order may not '
         'be cited as precedential authority, but may be called to the '
         'attention of the court in a subsequent stage of this case, in a '
         'related case, or in any case for purposes of collateral '
         'estoppel or res judicata. see second circuit rule 0.23.?'),
        ('third circuit',
         '(unpublished disposition )?notice: third circuit rule 21\(i\) '
         'states citations to federal decisions which have not been '
         'formally reported should identify the court, docket number and '
         'date.?'),
        ('fourth circuit',
         '(unpublished disposition )?notice: fourth circuit (local rule '
         '36\(c\)|i.o.p. 36.6) states that citation of unpublished '
         'dispositions is disfavored except for establishing res '
         'judicata, estoppel, or the law of the case and requires service '
         'of copies of cited unpublished dispositions of the fourth '
         'circuit.?'),
        ('fifth circuit',
         '(unpublished disposition )?notice: fifth circuit local rule '
         '47.5.3 states that unpublished opinions should normally be '
         'cited only when they establish the law of the case, are relied '
         'upon as a basis for res judicata or collateral estoppel, or '
         'involve related facts. if an unpublished opinion is cited, a '
         'copy shall be attached to each copy of the brief.?'),
        ('sixth circuit',
         '(unpublished disposition )?notice: sixth circuit rule 24\(c\) '
         'states that citation of unpublished dispositions is disfavored '
         'except for establishing res judicata, estoppel, or the law of '
         'the case and requires service of copies of cited unpublished '
         'dispositions of the sixth circuit.?'),
        ('seventh circuit',
         '(unpublished disposition )?notice: seventh circuit rule '
         '53\(b\)\(2\) states unpublished orders shall not be cited or '
         'used as precedent except to support a claim of res judicata, '
         'collateral estoppel or law of the case in any federal court '
         'within the circuit.?'),
        ('eighth circuit',
         '(unpublished disposition )?notice: eighth circuit rule 28a\(k\) '
         'governs citation of unpublished opinions and provides that (no '
         'party may cite an opinion not intended for publication unless '
         'the cases are related by identity between the parties or the '
         'causes of action|they are not precedent and generally should not '
         'be cited unless relevant to establishing the doctrines of res '
         'judicata, collateral estoppel, the law of the case, or if the '
         'opinion has persuasive value on a material issue and no '
         'published opinion would serve as well).?'),
        ('ninth circuit',
         '(unpublished disposition )?notice: ninth circuit rule 36-3 '
         'provides that dispositions other than opinions or orders '
         'designated for publication are not precedential and should not '
         'be cited except when relevant under the doctrines of law of the '
         'case, res judicata, or collateral estoppel.?'),
        ('tenth circuit',
         '(unpublished disposition )?notice: tenth circuit rule 36.3 '
         'states that unpublished opinions and orders and judgments have '
         'no precedential value and shall not be cited except for '
         'purposes of establishing the doctrines of the law of the case, '
         'res judicata, or collateral estoppel.?'),
        ('d.c. circuit',
         '(unpublished disposition )?notice: d.c. circuit local rule '
         '11\(c\) states that unpublished orders, judgments, and '
         'explanatory memoranda may not be cited as precedents, but '
         'counsel may refer to unpublished dispositions when the binding '
         'or preclusive effect of the disposition, rather than its '
         'quality as precedent, is relevant.?'),
        ('federal circuit',
         '(unpublished disposition )?notice: federal circuit local rule '
         '47.(6|8)\(b\) states that opinions and orders which are '
         'designated as not citable as precedent shall not be employed or '
         'cited as precedent. this does not preclude assertion of issues '
         'of claim preclusion, issue preclusion, judicial estoppel, law '
         'of the case or the like based on a decision of the court '
         'rendered in a nonprecedential opinion or order.?'),
    )
    status = 'Published'
    for test, regex in regexes:
        if test in s:
            s = re.sub(regex, s)
            status = 'Unpublished'

    s = titlecase(harmonize(clean_string(s)))
    return s, status


def get_court(case_tree):
    court_p_elems = case_tree.xpath('//p[@class = "court"]')
    # Often the court ends up in the parties field.
    parties_p_elems = case_tree.xpath("//p[@class= 'parties']")

    court_strs = ''
    for p in court_p_elems:
        court_strs += tostring(p).lower()
    for party in parties_p_elems:
        court_strs += tostring(party).lower()
    court_pairs = (
        ('first', 'ca1'),
        ('second', 'ca2'),
        ('third', 'ca3'),
        ('fourth', 'ca4'),
        ('fifth', 'ca5'),
        ('sixth', 'ca6'),
        ('seventh', 'ca7'),
        ('eighth', 'ca8'),
        ('ninth', 'ca9'),
        ('tenth', 'ca10'),
        ('eleventh', 'ca11'),
        ('columbia', 'cadc'),
        ('federal', 'cadc'),
        ('patent', 'ccpa'),
        ('claims', 'uscfc'),
    )
    court = None
    for test, result in court_pairs:
        if test in court_strs:
            court = result

    return court


def get_case_body(case_tree):
    body_elems = case_tree.xpath('//body/*[not(@id="footer")]')

    body = ''
    for elem in body_elems:
        body += tostring(elem)

    return body
