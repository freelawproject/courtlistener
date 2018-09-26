import os
import pickle
import re
from math import ceil

from django.conf import settings

conn_counties = ')|('.join([
    'Fairfield', 'Hartford', 'Litchfield', 'Middlesex', 'New Haven',
    'New London', 'Tolland', 'Windham',
])
ny_counties = ')|('.join([
    'Albany County', 'New York County', 'Kings County', 'Oneida County','Queens County',
    'Schenectady County', 'Westchester County',
])

# noinspection PyPep8
fd_pairs = (
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))?,? (court )?(of )?Colu(m|(in))bia', re.I), 'dcd'),
    # 1820-1824 --> ALD
    (re.compile('(^|\s)M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Alabama', re.I), 'almd'),
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Alabama', re.I), 'alnd'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Alabama', re.I), 'alsd'),
    (re.compile('Alaska', re.I), 'akd'),
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Arizona', re.I), 'azd'),
    # 1836-1851 --> ARD
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Arkansas', re.I), 'ared'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Arkansas', re.I), 'arwd'),
    (re.compile('(^|\s)C(\.|(entral))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Cal(ifornia)?', re.I), 'cacd'),
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Cal(ifornia)?', re.I), 'cand'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Cal(ifornia)?', re.I), 'casd'),
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Cal(ifornia)?', re.I), 'caed'),
    # No longer exists. Existed 1866-07-27 to 1886-08-05
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?California', re.I), 'californiad'),  # Must go last for Cal.
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Colo(rado)?', re.I), 'cod'),
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Conn', re.I), 'ctd'),
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Delaware', re.I), 'ded'),
    # 1845 to 1847 --> FLD
    (re.compile('(^|\s)M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Fl(orid)?a', re.I), 'flmd'),
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Fl(orid)?a', re.I), 'flnd'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Fl(orid)?a', re.I), 'flsd'),
    # 1789 to 1848 --> GAD
    (re.compile('(^|\s)M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?G(a|(eorgia))', re.I), 'gamd'),
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?G(a|(eorgia))', re.I), 'gand'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?G(a|(eorgia))', re.I), 'gasd'),
        (re.compile('Waycross Division', re.I), 'gasd'),
    (re.compile('Hawai', re.I), 'hid'),
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Idaho', re.I), 'idd'),
    # From 1819-1855 there existed a district of illinios court.
    # From 1855-1905 three existed northern and southern district courts.
    # From 1905-1978 there existed northern, eastern and southern district courts.
    # From 1978-present there exists northern, central and southern courts in Illinois.
    (re.compile('(^|\s)C(\.|(entral))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Ill(inois)?', re.I), 'ilcd'),
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Ill(inois)?', re.I), 'ilnd'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Illinois', re.I), 'ilsd'),
    # Abolished. 1905-03-03 to 1978-10-02
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Illinois', re.I), 'illinoised'),
    # Abolished. 1819-03-03 to 1855-02-13
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Illinois', re.I), 'illinoisd'), # Must go last
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Indiana', re.I), 'innd'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Indiana', re.I), 'insd'),
    # Abolished. 1817-03-03 to 1928-04-21
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Indiana', re.I), 'indianad'), # Must go last
    # 1845-1882 --> IAD
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Iowa', re.I), 'iand'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Iowa', re.I), 'iasd'),
    (re.compile('Kansas', re.I), 'ksd'),
    # 1789 to 1901 --> KYD
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Kentucky', re.I), 'kyed'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|(ist(\.|(rict)))),? ?(of )?Kentucky', re.I), 'kywd'),
    # 1812-1823 and 1866-1881 --> LAD
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Louisiana', re.I), 'laed'),
    (re.compile('Eastern District, Louisiana', re.I), 'laed'),
    (re.compile('(^|\s)M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Louisiana', re.I), 'lamd'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Louisiana', re.I), 'lawd'),
    (re.compile('(^|\s)D(\.|:|,|(istrict))? ?(of )?Maine', re.I), 'med'),
    (re.compile('(^|\s)D(\.|(istrict))? ?(of )?Maryland', re.I), 'mdd'),
        (re.compile(', Maryland', re.I), 'mdd'),
        (re.compile('Maryland Admiralty', re.I), 'mdd'),
    (re.compile('(^|\s)D?\.? ?(of )?Mass(achusetts)?', re.I), 'mad'),
    # 1836-1863 --> MID
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Michigan', re.I), 'mied'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Michigan', re.I), 'miwd'),
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Minn(\.|(esota))', re.I), 'mnd'),
    # 1818-1838 --> MSD
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Mississippi', re.I), 'msnd'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Mississippi', re.I), 'mssd'),
    # 1822-1857 --> MOD
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|(istrict))?,? ?(of )?(the )?Missouri', re.I), 'moed'),
        (re.compile('(^|\s)District Court,? C|S\. D\. Missouri,? E\. ?D\.', re.I), 'moed'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Missouri', re.I), 'mowd'),
        (re.compile('(^|\s)District Court,? C|S\. D\. Missouri,? W\. ?D\.', re.I), 'mowd'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Missouri', re.I), 'mosd'),
        (re.compile('Missouri, W\.D', re.I), 'mowd'),
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Montana', re.I), 'mtd'),
    (re.compile('(^|\s)D(\.|(istrict))? ?(of )?Nebraska', re.I), 'ned'),
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Nevada', re.I), 'nvd'),
    (re.compile('New Hampshire', re.I), 'nhd'),
    # 1789-1801    --> NJD
    # 1801-1802    --> NJED and NJWD
    # 1802-present --> NJD
    (re.compile('New Jersey', re.I), 'njd'),
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?New Mexico', re.I), 'nmd'),
    # 1789-1814 --> NYD
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|(istrict)),? ?(of )?N(\.|(ew)) ?Y(ork)?', re.I), 'nyed'),
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?N(\.|(ew)) ?Y(ork)?', re.I), 'nynd'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?N(\.|(ew)) ?Y(ork)?', re.I), 'nysd'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?N(\.|(ew)) ?Y(ork)?', re.I), 'nywd'),
    # 1790-1794 --> NCD
    # 1794-1797 --> Three district courts with a single judge:
    #                   - District of Edenton
    #                   - District of New Bern
    #                   - District of Wilmington
    # 1797-1802 --> NCD
    # 1802-1872 --> Three district courts with a single judge:
    #                   - District of Albermarle
    #                   - District of Cape Fear
    #                   - District of Pamptico
    # 1872-1927 --> NCED, NCWD
    # 1927-present --> NCED, NCWD, NCMD
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?N(\.|(orth)) Car?olina', re.I), 'nced'),
    (re.compile('(^|\s)M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?N(\.|(orth)) Car?olina', re.I), 'ncmd'),
        (re.compile('Greensboro Division', re.I), 'ncmd'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?N(\.|(orth)) Car?olina', re.I), 'ncwd'),
        (re.compile('Charlotte Division', re.I), 'ncwd'),
    (re.compile('North Dakota', re.I), 'ndd'),
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Ohio', re.I), 'ohnd'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Ohio', re.I), 'ohsd'),
    # Abolished. 1803-02-19 to 1855-02-10
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Ohio', re.I), 'ohiod'), # Must be the last court!
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Oklahoma', re.I), 'oked'),
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Oklahoma', re.I), 'oknd'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Oklahoma', re.I), 'okwd'),
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?Oregon', re.I), 'ord'),
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?P(a|(ennsylvania))', re.I), 'paed'),
    (re.compile('(^|\s)M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?P(a|(ennsylvania))', re.I), 'pamd'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?P(a|(ennsylvania))', re.I), 'pawd'),
    # Abolished. 1789-09-24 to 1818-04-20
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? ?(of )?P(a|(ennsylvania))', re.I), 'pennsylvaniad'),  # Must go last
    (re.compile('Rhode Island', re.I), 'rid'),
    # Abolished. 1823-02-21 to 1965-10-07
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?South Carolina', re.I), 'southcarolinaed'),
    # Abolished. 1823-02-21 to 1965-10-07
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?S(\.|(outh))? C(\.|(arolina))?', re.I), 'southcarolinawd'),
    (re.compile('(^|\s)D(\.|:|,|(ist(\.|(rict))))? (Court)?,? ?(of )?S(\.|(outh))? C(\.|(arolina))?', re.I), 'scd'),  # Must go last!
    (re.compile('South Dakota', re.I), 'sdd'),
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Tenn(\.|(essee))', re.I), 'tned'),
    (re.compile('(^|\s)M(\.|(iddle))? ?D(\.|(istrict))?,? ?(of )?Tenn(\.|(essee))', re.I), 'tnmd'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Tenn(\.|(essee))', re.I), 'tnwd'),
    # Abolished. 1797-01-31 to 1839-06-18
    (re.compile('(^|\s)D(\.|(istrict))? ?(of )?Tennessee', re.I), 'tennessed'),  # Must be the last court!
    # 1845-1857 --> TXD
    # 1857-1879 --> TXED, TXWD
    # 1879-1902 --> TXED, TXWD, TXND
    # 1902-present --> TXED, TXWD, TXND, TXSD
    (re.compile('(^|\s)E ?(\.|(astern))? ?D ?(\.|:|(istrict)),? ?(of )?Tex(\.|(as))', re.I), 'txed'),
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Tex(\.|(as))', re.I), 'txnd'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|(istrict)),? ?(of )?Texas', re.I), 'txsd'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Tex(\.|(as))', re.I), 'txwd'),
        (re.compile('Midland/Odessa', re.I), 'txwd'),
    (re.compile('Utah', re.I), 'utd'),
    (re.compile('Vermont', re.I), 'vtd'),
    # 1789-1801 --> VAD
    # 1801-1802 --> District of Virginia, District of Norfolk, District of Potomac
    # 1802-1819 --> VAD
    # 1819-1864 --> VAED, VAWD
    # 1864-1871 --> VAD
    # 1871-present --> VAWD, VAED
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Virginia', re.I), 'vaed'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Virginia', re.I), 'vawd'),
        (re.compile('Abingdon', re.I), 'vawd'),
        (re.compile('Big Stone Gap', re.I), 'vawd'),
        (re.compile('Lynchburg', re.I), 'vawd'),
    # 1890-1905 --> WAD
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Wash(ington)?', re.I), 'waed'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Wash(ington)?', re.I), 'wawd'),
    # 1864-1901 --> WVD
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?W(\.|(est)) V(a|(irginia))', re.I), 'wvnd'),
    (re.compile('(^|\s)S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?W(\.|(est)) V(a|(irginia))', re.I), 'wvsd'),
        (re.compile('West Virginia, at Charleston', re.I), 'wvsd'),
        (re.compile('Parkersburg Division', re.I), 'wvsd'),
    # 1848-1870 --> WID
    (re.compile('(^|\s)E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Wisconsin', re.I), 'wied'),
        (re.compile('D\. Wisconsin, E\. D', re.I), 'wied'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Wisconsin', re.I), 'wiwd'),
    (re.compile('Wyoming', re.I), 'wyd'),

    # Territories and commonwealths
    # Abolished. 1937-07-26 to 1982-03-31
    (re.compile('Canal Zone', re.I), 'canalzoned'),
    (re.compile('Guam', re.I), 'gud'),
    (re.compile('(^|\s)N(\.|(orthern)) Mariana', re.I), 'nmid'),
    (re.compile('Puerto Rico', re.I), 'prd'),
    (re.compile('Virgin Islands', re.I), 'vid'),

    # Federal speciality courts
    (re.compile('U\. S\. Court of Customs Appeals', re.I), 'ccpa'),
    (re.compile(u'Commerce Court', re.I), 'com'),
    (re.compile(u'Court of Claims', re.I), 'cc'),
    (re.compile(u'(^|\s)U\. S\. Court of Customs and Patent Appeals', re.I), 'ccpa'),
    (re.compile(u'(^|\s)U\. S\. Court of International Trade', re.I), 'cit'),
    (re.compile(u'(^|\s)U\. S\. Customs Court', re.I), 'cusc'),
    (re.compile(u'(^|\s)U\. S\. District Court for the District of Columbia', re.I), 'dcd'),

    # this was a special circuit court when california was first founded, it
    # only had one judge
    (re.compile(u'(^|\s)U\. S\. Circuit Court for the Districts of California', re.I), 'caca'),

    # this was a district court for the territory of orleans
    (re.compile(u'District of Orleans', re.I), 'orld'),

    # these state district courts have since been split
    (re.compile(u'District of Alabama', re.I), 'ald'),
    (re.compile(u'District of Florida', re.I), 'fld'),
    (re.compile(u'District of Georgia', re.I), 'gad'),
    (re.compile(u'District of Iowa', re.I), 'iad'),
    (re.compile(u'District of Kentucky', re.I), 'kyd'),
    (re.compile(u'District of Louisiana', re.I), 'lad'),
    (re.compile(u'District of Michigan', re.I), 'michd'),
    (re.compile(u'District of Mississippi', re.I), 'missd'),
    (re.compile(u'District of Missouri', re.I), 'mod'),
    (re.compile(u'District of New York', re.I), 'nyd'),
    (re.compile(u'District of North Carolina', re.I), 'ncd'),
    (re.compile(u'District of Texas', re.I), 'texd'),
    (re.compile(u'District of Virginia', re.I), 'vad'),
    (re.compile(u'District of Washington', re.I), 'washd'),
    (re.compile(u'District of West Virginia', re.I), 'wvad'),
    (re.compile(u'District of Wisconsin', re.I), 'wisd'),
)

ca_pairs = (
    (re.compile(u'Supreme Court of the United States', re.I), 'scotus'),

    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the First Circuit', re.I), 'ca1'),
    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the Second Circuit', re.I), 'ca2'),
    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the Third Circuit', re.I), 'ca3'),
    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the Fourth Circuit', re.I), 'ca4'),
    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the Fifth Circuit', re.I), 'ca5'),
    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the Sixth Circuit', re.I), 'ca6'),
    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the Seventh Circuit', re.I), 'ca7'),
    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the Eighth Circuit', re.I), 'ca8'),
    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the Ninth Circuit', re.I), 'ca9'),
    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the Tenth Circuit', re.I), 'ca10'),
    (re.compile(u'(^|\s)U\. S\. ((Circuit Courts?)|(Court of Appeals)) for the Eleventh Circuit', re.I), 'ca11'),
    (re.compile(u'(^|\s)U\. S\. Court of Appeals for the District of Columbia Circuit', re.I), 'cadc'),
    (re.compile(u'(^|\s)U\. S\. Court of Appeals for the Federal Circuit', re.I), 'cafc'),
)

# noinspection PyPep8
fb_pairs = (
    (re.compile('(^|\s)D(\.|(istrict)) of Columbia', re.I), 'dcb'),
    (re.compile('(^|\s)M(\.|(iddle))? ?D(\.|(istrict))? (of )?Alabama', re.I), 'almb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? (of )?Alabama', re.I), 'alnb'),
    (re.compile('(^|\s)S\.? ?D(\.|(istrict))? (of )?Alabama', re.I), 'alsb'),
    (re.compile('(^|\s)D\. Alaska', re.I), 'akb'),
    (re.compile('(^|\s)D(\.|(istrict))? ?Arizona', re.I), 'arb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? ?(of )?Arkansas', re.I), 'areb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? ?(of )?Arkansas', re.I), 'arwb'),
    (re.compile('(^|\s)C\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', re.I), 'cacb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', re.I), 'caeb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', re.I), 'canb'),
    (re.compile('(^|\s)S\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', re.I), 'casb'),
    (re.compile('(^|\s)D(\.|(istrict)) ?(of )?Colorado', re.I), 'cob'),
    (re.compile('Connecticut', re.I), 'ctb'),
    (re.compile('(^|\s)D(\.|(istrict))? (of )?Delaware', re.I), 'deb'),
    (re.compile('(^|\s)M(\.|(iddle))? ?D(\.|(istrict))? ?(of )?Florida', re.I), 'flmb'),
        (re.compile('Florida, Tampa Division', re.I), 'flmb'),
        (re.compile('Florida, Jacksonville Division', re.I), 'flmb'),
    (re.compile('(^|\s)N(\.|(orthern))? ?D(\.|(istrict))? (of )?Florida', re.I), 'flnb'),
    (re.compile('(^|\s)S\. ?D(\.|(istrict))? (of )?Florida', re.I), 'flsb'),
    (re.compile('(^|\s)M\.? ?D(\.|(istrict))? (of )?Georgia', re.I), 'gamb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? (of )?Georgia', re.I), 'ganb'),
        (re.compile('Atlanta Division', re.I), 'ganb'),
    (re.compile('(^|\s)S\. ?D(\.|(istrict))? Georgia', re.I), 'gasb'),
    (re.compile('(^|\s)D(\.|(istrict))? ?Hawai', re.I), 'hib'),
    (re.compile('(^|\s)D\. Idaho', re.I), 'idb'),
    (re.compile('(^|\s)C\.? ?D(\.|(istrict))? ?(of )?Ill(inois)?', re.I), 'ilcb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? ?(of )?Ill(inois)?', re.I), 'ilnb'),
    (re.compile('(^|\s)S\.? ?D(\.|(istrict))? ?(of )?Ill(inois)?', re.I), 'ilsb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? ?(of )?Indiana', re.I), 'innb'),
    (re.compile('(^|\s)S\.D\. (of )?Indiana', re.I), 'insb'),
    (re.compile('(^|\s)N\. ?D(\.|(istrict))? Iowa', re.I), 'ianb'),
    (re.compile('(^|\s)S\. ?D(\.|(istrict))? (of )?Iowa', re.I), 'iasb'),
    (re.compile('(^|\s)(D|M)(\.|(istrict)) (of )?Kan(sas)?', re.I), 'ksb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? (of )?Kentucky', re.I), 'kyeb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? (of )?Kentucky', re.I), 'kywb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? (of )?Loui?siana', re.I), 'laeb'),
        (re.compile('Eastern District, Louisiana', re.I), 'laeb'),
    (re.compile('(^|\s)M\.? ?D(\.|(istrict))? (of )?Loui?siana', re.I), 'lamb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? (of )?Loui?siana', re.I), 'lawb'),
    (re.compile('(^|\s)D\. Maine', re.I), 'meb'),
    (re.compile('Maryland', re.I), 'mdb'),
    (re.compile('D(\.|(istrict))? ?(of )?Mass', re.I), 'mab'),
        (re.compile(', Massachusetts', re.I), 'mab'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? (of )?Michigan', re.I), 'mieb'),
    (re.compile('(^|\s)W\.D(\.|(istrict))? (of )?Michigan', re.I), 'miwb'),
    (re.compile('(^|\s)D(\.|(istrict))? ?Minnesota', re.I), 'mnb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? (of )?Mississippi', re.I), 'msnb'),
    (re.compile('(^|\s)S\.? ?D(\.|(istrict))? (of )?Mississippi', re.I), 'mssb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? ?(of )?Missouri', re.I), 'moeb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? ?(of )?Missouri', re.I), 'mowb'),
    (re.compile('(^|\s)D\. Montana', re.I), 'mtb'),
    # Here we avoid a conflict with state abbreviations
    (re.compile('(^|\s)D(\.|(istrict))? (of )?Neb(raska)?', re.I), 'nebraskab'),
    (re.compile('Nevada', re.I), 'nvb'),
    (re.compile('New Hampshire', re.I), 'nhb'),
        (re.compile('D\.N\.H', re.I), 'nhb'),
    (re.compile('(^|\s)D(\.|(istrict))? ?New Jersey', re.I), 'njb'),
        (re.compile(', New Jersey', re.I), 'njb'),
    (re.compile('New Mexico', re.I), 'nmb'),
        (re.compile('State of New Mexico', re.I), 'nmb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? (of )?New York', re.I), 'nyeb'),
        (re.compile('E\.D\.N\.Y', re.I), 'nyeb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? (of )?New York', re.I), 'nynb'),
    (re.compile('(^|\s)S\. ?D(\.|(istrict))? (of )?New York', re.I), 'nysb'),
        (re.compile('Southern District of New York', re.I), 'nysb'),
        (re.compile('S.D.N.Y', re.I), 'nysb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? (of )?New York', re.I), 'nywb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? (of )?North Carolina', re.I), 'nceb'),
        (re.compile('North Carolina,? Raleigh Division', re.I), 'nceb'),
    (re.compile('(^|\s)M\.? ?D(\.|(istrict))? (of )?North Carolina', re.I), 'ncmb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? (of )?North Carolina', re.I), 'ncwb'),
    (re.compile('North Dakota', re.I), 'ndb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? (of )?Ohio', re.I), 'ohnb'),
        (re.compile('Northern District of Ohio', re.I), 'ohnb'),
    (re.compile('(^|\s)S\. ?D(\.|(istrict))? (of )?Ohio', re.I), 'ohsb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? (of )?Oklahoma', re.I), 'okeb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? (of )?Oklahoma', re.I), 'oknb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? (of )?Oklahoma', re.I), 'okwb'),
    (re.compile('Oregon', re.I), 'orb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? (of )?Pennsylvania', re.I), 'paeb'),
    (re.compile('(^|\s)M\.? ?D(\.|(istrict))? (of )?Pennsylvania', re.I), 'pamb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? (of )?Pennsylvania', re.I), 'pawb'),
    (re.compile('(^|\s)D(\.|(istrict))? ?Rhode Island', re.I), 'rib'),
        (re.compile(', Rhode Island', re.I), 'rib'),
        (re.compile(', D\.R\.I', re.I), 'rib'),
    (re.compile('(^|\s)D(\.|(istrict))? ?(of )?South Carolina', re.I), 'scb'),
        (re.compile('D\.S\.C', re.I), 'scb'),
    (re.compile('(^|\s)D\. South Dakota', re.I), 'sdb'),
        (re.compile(', South Dakota', re.I), 'sdb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? (of )?Te(r|n)n(essee)?', re.I), 'tneb'),
    (re.compile('(^|\s)M\.? ?D(\.|(istrict))? (of )?Tenn(essee)?', re.I), 'tnmb'),
        (re.compile('Middle District of Tennessee', re.I), 'tnmb'),
        (re.compile('M\.D\.S\. Tennessee', re.I), 'tnmb'),
        (re.compile('Nashville', re.I), 'tnmb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? (of )?Tennessee', re.I), 'tnwb'),
    (re.compile('(^|\s)D\. Tennessee', re.I), 'tennesseeb'),  # Only exists 1797-1801
    (re.compile('(^|\s)E\.? ?D ?(\.|(istrict))? (of )?Texas', re.I), 'txeb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? (of )?Texas', re.I), 'txnb'),
    (re.compile('(^|\s)S\.? ?D(\.|(istrict))? (of )?Texas', re.I), 'txsb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? (of )?Texas', re.I), 'txwb'),
    (re.compile('Utah', re.I), 'utb'),
    (re.compile('(^|\s)D(\.|(istrict))? ?(of )?Vermont', re.I), 'vtb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))?,? ?(of )?Virginia', re.I), 'vaeb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))?,? ?(of )?Virginia', re.I), 'vawb'),
        (re.compile('Big Stone Gap', re.I), 'vawb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? (of )?Washington', re.I), 'waeb'),
    (re.compile('(^|\s)W\.? ?D(\.|(istrict))? (of )?Washington', re.I), 'wawb'),
    (re.compile('(^|\s)N\.? ?D(\.|(istrict))? (of )?W(\.|(est)) Virginia', re.I), 'wvnb'),
    (re.compile('(^|\s)S\.? ?D(\.|(istrict))? (of )?W(\.|(est)) Virginia', re.I), 'wvsb'),
    (re.compile('(^|\s)E\.? ?D(\.|(istrict))? (of )?Wis(consin)?', re.I), 'wieb'),
    (re.compile('(^|\s)W(\.|(estern))? ?D(\.|(istrict))? (of )?Wis(consin)?', re.I), 'wiwb'),
    (re.compile('(^|\s)D\. Wyoming', re.I), 'wyb'),

    # Bankruptcy territories and commonwealths
    (re.compile('Guam', re.I), 'gub'),
    (re.compile('Northern Mariana', re.I), 'nmib'),
    (re.compile('Puerto Rico', re.I), 'prb'),
    (re.compile('Virgin Islands', re.I), 'vib'),
)

# noinspection PyPep8
state_pairs = (
    (re.compile('D((istrict)|\.) (of )?C((olumbia)|\.) Court of Appeals', re.I), 'dc'),
        (re.compile('D((istrict)|\.) (of )?C((olumbia)|\.) Municipal Court of Appeals', re.I), 'dc'),
            (re.compile('Municipal Court of Appeals? (for the )?D((istrict)|\.) (of )?C((olumbia)|\.)', re.I), 'dc'),
        (re.compile('Supreme Court of the D((istrict)|\.) (of )?C((olumbia)|\.)', re.I), 'dc'),
    (re.compile('Supreme Court of Alabama', re.I), 'ala'),
    (re.compile('Court of Criminal Appeals? of Alabama', re.I), 'alacrimapp'),
        (re.compile('Alabama Court of Criminal Appeals?', re.I), 'alacrimapp'),
    (re.compile('Court of Civil Appeals? of Alabama', re.I), 'alacivapp'),
    (re.compile('Court of Appeals? of Alabama', re.I), 'alactapp'),  # Abolished.
    (re.compile('Supreme Court of Alaska', re.I), 'alaska'),
    (re.compile('Court of Appeals? of Alaska', re.I), 'alaskactapp'),
    (re.compile('Supreme Court of Arizona', re.I), 'ariz'),
    (re.compile('Court of Appeals,? of Arizona', re.I), 'arizctapp'),
    (re.compile('Tax Court of Arizona', re.I), 'ariztaxct'),
    (re.compile('Supreme Court of Arkansas', re.I), 'ark'),
    (re.compile('Court of Appeals? of Arkansas', re.I), 'arkctapp'),

    (re.compile('Supreme Court of California', re.I), 'cal'),
    (re.compile('California Court of Appeals', re.I), 'calctapp'),
        (re.compile('Court of Appeals? of California', re.I), 'calctapp'),
    (re.compile('Appellate Division, Superior Court', re.I), 'calappdeptsuperct'),
        (re.compile('California Superior Court\.? +Appellate ((Division)|(Department))', re.I), 'calappdeptsuperct'),

    (re.compile('Supreme Court of Colorado', re.I), 'colo'),
    (re.compile('Office of the Presiding Disciplinary Judge of the Supreme Court of  Colorado', re.I), 'colo'),
    (re.compile('Colorado Court of Appeals', re.I), 'coloctapp'),
        (re.compile('Court of Appeals? of Colorado', re.I), 'coloctapp'),

    (re.compile('Supreme Court of Connecticut', re.I), 'conn'),
    (re.compile('Connecticut Appellate Court', re.I), 'connappct'),
        (re.compile('Appellate Court of Connecticut', re.I), 'connappct'),
        # This court is terminated, succeeded by the appellate court of conn.
        (re.compile('Appellate Session of the Superior Court', re.I), 'connsuperct'),
    (re.compile('Superior Court of Connecticut', re.I), 'connsuperct'),
        (re.compile('Connecticut Superior Court', re.I), 'connsuperct'),
        (re.compile('Review Division Of The Superior Court', re.I), 'connsuperct'),
        # Merged with Superior Court on July 1, 1978
        (re.compile('Court of Common Pleas,? +((%s))' % conn_counties, re.I), 'connsuperct'),
        (re.compile('Superior Court,? +((%s))' % conn_counties, re.I), 'connsuperct'),

    (re.compile('Supreme Court of (the State of )?Delaware', re.I), 'del'),
        (re.compile('Delaware Supreme Court', re.I), 'del'),
        (re.compile('(High )?Court of Errors and Appeals (Court )?of Delaware', re.I), 'del'),
        # This is a guess, but there's only one case in this jurisdiction and
        # it has to do with a governor that passed in office. Seems like
        # Supreme court level stuff.
        (re.compile('In vacation of Delaware', re.I), 'del'),
    (re.compile('Court of Chancery of (the State of )?Delaware', re.I), 'delch'),
        (re.compile('Chancery Court of Delaware', re.I), 'delch'),
    (re.compile('Superior Court of (the State of )?Delaware', re.I), 'delsuperct'),
        # These two merged into the Superior court of Delaware
        (re.compile('Orphans\'? Court( Court)? of Delaware', re.I), 'delsuperct'),
        (re.compile('Court of General Sessions', re.I), 'delsuperct'),
        (re.compile('Court of Oyer and Terminer of Delaware', re.I), 'delsuperct'),
        (re.compile('Court of Common Pleas,? (Court )?of Delaware', re.I), 'delsuperct'),
        (re.compile('Court of Quarter Sessions,? (Court )?of Delaware', re.I), 'delsuperct'),
        (re.compile('Courts of General Sessions and (of )?Oyer and Terminer of Delaware', re.I), 'delsuperct'),
    (re.compile('Circuit Court of ((the )?United States of )?Delaware', re.I), 'circtdel'),
        (re.compile('Circuit Court,  Delaware', re.I), 'circtdel'),
        (re.compile('Circuit Court.*Dover', re.I), 'circtdel'),
    (re.compile('Family Court of Delaware', re.I), 'delfamct'),
    (re.compile('Court on the Judiciary of Delaware', re.I), 'deljudct'),
        (re.compile('Delaware Court on the Judiciary', re.I), 'deljudct'),

    (re.compile('Supreme Court of Florida', re.I), 'fla'),
        (re.compile('Supreme Court.*Nassau County', re.I), 'fla'),
        (re.compile('Court of Florida, Division B', re.I), 'fla'),
    (re.compile('District Courts? of Appeal, ((Lakeland,)|(of) )?Florida', re.I), 'fladistctapp'),

    (re.compile('Supreme Court of Georgia', re.I), 'ga'),
    (re.compile('Court of Appeals? of Georgia', re.I), 'gactapp'),

    (re.compile('Supreme Court of Hawai', re.I), 'haw'),
    (re.compile('Intermediate Court (of )?Appeals? .*Hawai', re.I), 'hawapp'),
        (re.compile('Court of Appeals? of Hawai', re.I), 'hawapp'),
        (re.compile('Hawaii Court of Appeals?', re.I), 'hawapp'),
        (re.compile('Hawaii Intermediate Court of Appeals?', re.I), 'hawapp'),

    (re.compile('Supreme Court of (the state of )?Idaho', re.I), 'idaho'),
    (re.compile('Court of Appeals? of Idaho', re.I), 'idahoctapp'),
        (re.compile('Idaho Court of Appeals', re.I), 'idahoctapp'),

    (re.compile('Supreme Court of Illinois', re.I), 'ill'),
    (re.compile('Appellate Court of Illinois', re.I), 'illappct'),
        (re.compile('Illinois Appellate Court', re.I), 'illappct'),

    (re.compile('Supreme Court of Indiana', re.I), 'ind'),
    (re.compile('Court of Appeals? ((of)|(in)) Indiana', re.I), 'indctapp'),
        (re.compile('Appe((llate)|(als)) Court of Indiana', re.I), 'indctapp'),
        (re.compile('Indiana Court of Appeals', re.I), 'indctapp'),
    (re.compile('Tax Court of Indiana', re.I), 'indtc'),
        (re.compile('Indiana Tax Court', re.I), 'indtc'),

    (re.compile('Supreme Court of Iowa', re.I), 'iowa'),
    (re.compile('Court of Appeals? (of )?Iowa', re.I), 'iowactapp'),
        (re.compile('Iowa Court of Appeals', re.I), 'iowactapp'),

    (re.compile('Supreme Court of Kansas', re.I), 'kan'),
    (re.compile('Court of Appeals? of Kansas', re.I), 'kanctapp'),

    (re.compile('Supreme Court of Kentucky', re.I), 'ky'),
    (re.compile('Court of Appeals? of Kentucky', re.I), 'kyctapp'),

    (re.compile('Supreme Court of Louisiana', re.I), 'la'),
    (re.compile('Court of Appeals? of Louisiana', re.I), 'lactapp'),
    (re.compile('Louisiana Circuit Courts of Appeal', re.I), 'lactapp'),

    (re.compile('Supreme Judicial Court of Maine', re.I), 'me'),

    (re.compile('Court of Appeals? of Maryland', re.I), 'md'),
        (re.compile('Supreme Court of Maryland', re.I), 'md'),
    (re.compile('Court of Special Appeals? of Maryland', re.I), 'mdctspecapp'),

    (re.compile('Supreme (Judicial )?Court of Massachusetts', re.I), 'mass'),
    (re.compile('Appeals? Court of Massachusetts', re.I), 'massappct'),
    (re.compile('Massachusetts Superior Court', re.I), 'masssuperct'),
    (re.compile('Massachusetts Appellate Division', re.I), 'massdistct'),

    (re.compile('Supreme Court of Michigan', re.I), 'mich'),
    (re.compile('Michigan Court of Appeals', re.I), 'michctapp'),
        (re.compile('Court of Appeals? of Michigan', re.I), 'michctapp'),

    (re.compile('Supreme Court of Minnesota', re.I), 'minn'),
    (re.compile('Court of Appeals? of Minnesota', re.I), 'minnctapp'),
        (re.compile('Minnesota Court of Appeals?', re.I), 'minnctapp'),

    (re.compile('Supreme Court of Mississippi', re.I), 'miss'),
        # Historical name.
        (re.compile('High Court of Errors and Appeals, Mississippi', re.I), 'miss'),
        # Only one case. Have it on authority from Miss. Supreme Court and
        # Law Library that this is just another name for the Supreme Court.
        (re.compile('Superior Court of Mississippi', re.I), 'miss'),
    (re.compile('Court of Appeals? of Mississippi', re.I), 'missctapp'),

    (re.compile('Supreme Court of Missouri', re.I), 'mo'),
    (re.compile('Missouri Court of Appeals', re.I), 'moctapp'),
        (re.compile('St\. Louis,? Court of Appeals', re.I), 'moctapp'),
        (re.compile('Kansas City.? (of )?Court of appeals', re.I), 'moctapp'),
        (re.compile('Springfield,? Court of appeals', re.I), 'moctapp'),

    (re.compile('Supreme Court of Montana', re.I), 'mont'),
    (re.compile('Tax Appeal Board of the State of Montana', re.I), 'monttc'),

    (re.compile('Supreme Court of Nebraska', re.I), 'neb'),
    (re.compile('Court of Appeals? of Nebraska', re.I), 'nebctapp'),
        (re.compile('Nebraska Court of Appeals', re.I), 'nebctapp'),

    (re.compile('Supreme Court of Nevada', re.I), 'nev'),

    (re.compile('Supreme Court of New Hampshire', re.I), 'nh'),

    (re.compile('Supreme Court of New Jersey', re.I), 'nj'),
    (re.compile('Superior Court of New Jersey', re.I), 'njsuperctappdiv'),
        # Terminated as part of 1947 NJ constitution, and folded into sup.
        (re.compile('Prerogative Court', re.I), 'njsuperctappdiv'),
    (re.compile('Tax Court of New Jersey', re.I), 'njtaxct'),

    (re.compile('Supreme Court of New Mexico', re.I), 'nm'),
    (re.compile('Court of Appeals? of New Mexico', re.I), 'nmctapp'),
        (re.compile('New Mexico Court of Appeals', re.I), 'nmctapp'),

    (re.compile('Court of Appeals? of (the State of )?New York', re.I), 'ny'),
    (re.compile('Appellate Division of the Supreme Court of (the State of )?New York', re.I), 'nyappdiv'),
        (re.compile('Supreme Court.*((%s))' % ny_counties, re.I), 'nyappdiv'),
    (re.compile('Supreme Court of the State of New York', re.I), 'nysupct'),
    (re.compile('Family Court.*New York', re.I), 'nyfamct'),
    (re.compile('Surrogate\'s Court', re.I), 'nysurct'),
    (re.compile('Criminal Court of the City of New York', re.I), 'nycrimct'),
    (re.compile('Civil Court of the City of New York', re.I), 'nycivct'),
    (re.compile('Appellate Term of the Supreme Court of New York', re.I), 'nyappterm'),

    (re.compile('Supreme Court of North Carolina', re.I), 'nc'),
        (re.compile('Court of Conference', re.I), 'nc'),
        # Only one case in here, and it's basically just a reference to a
        # different case.
        (re.compile('Conference at Raleigh', re.I), 'nc'),
    (re.compile('Court of Appeals? (of )?North Carolina', re.I), 'ncctapp'),
        (re.compile('North Carolina Court of Appeals', re.I), 'ncctapp'),
    (re.compile('Superior Court of North Carolina', re.I), 'ncsuperct'),
        (re.compile('In the General Court of Justice Superior Court Division', re.I), 'ncsuperct'),

    (re.compile('Supreme Court of North Dakota', re.I), 'nd'),
    (re.compile('Court of Appeals? of North Dakota', re.I), 'ndctapp'),

    (re.compile('Supreme Court of Ohio', re.I), 'ohio'),
    (re.compile('Court of Appeals of Ohio', re.I), 'ohioctapp'),
        (re.compile('Ohio Court of Appeals', re.I), 'ohioctapp'),
    (re.compile('Court of Claims of Ohio', re.I), 'ohioctcl'),

    (re.compile('Supreme Court (of )?Oklahoma', re.I), 'okla'),
    (re.compile('Court of Criminal Appeals? (of )?Oklahoma', re.I), 'oklacrimapp'),
        (re.compile('Criminal Courts? of Appeals? of Oklahoma', re.I), 'oklacrimapp'),
    (re.compile('Court of Civils? Appeals? of Oklahoma', re.I), 'oklacivapp'),
    (re.compile('Oklahoma Court of Civil Appeals?', re.I), 'oklacivapp'),
        # When they refer to simply the "Court of Appeals" they mean the the civil court
        (re.compile('Court of Appeals?,? (civil )?(of )?(State )?(of )?Oklahoma', re.I), 'oklacivapp'),
    (re.compile('Oklahoma Judicial Ethics Advisory Panel', re.I), 'oklajeap'),
    (re.compile('Court on the Judiciary of Oklahoma', re.I), 'oklacoj'),

    (re.compile('Supreme Court (((for)|(of)) the State )?of (the )?Oregon', re.I), 'or'),
        (re.compile('Oregon Supreme Court', re.I), 'or'),
    (re.compile('Court of Appeals? of (the )?(state of )?Oregon', re.I), 'orctapp'),
        (re.compile('oregon court of appeals', re.I), 'orctapp'),
    (re.compile('Oregon Tax Court', re.I), 'ortc'),

    (re.compile('Supreme Court of Pennsylvania', re.I), 'pa'),
    (re.compile('Superior Court of Pennsylvania', re.I), 'pasuperct'),
    (re.compile('Commonwealth Court of Pennsylvania', re.I), 'pacommwct'),
    (re.compile('Court of Judicial Discipline of Pennsylvania', re.I), 'cjdpa'),

    (re.compile('Supreme Court,? of Rhode Island', re.I), 'ri'),
    (re.compile('State of Rhode Island, Superior Court', re.I), 'risuperct'),

    (re.compile('Supreme Court of South Carolina', re.I), 'sc'),
    (re.compile('Court of Appeals? of South Carolina', re.I), 'scctapp'),

    (re.compile('Supreme Court of South Dakota', re.I), 'sd'),

    (re.compile('Supreme Court of Tennessee', re.I), 'tenn'),
    (re.compile('(Supreme )?Court of Errors and Appeals, Nashville', re.I), 'tenn'),
    (re.compile('Court of Appeals? (of )?Tennessee', re.I), 'tennctapp'),
        (re.compile('Tennessee Court of Appeals', re.I), 'tennctapp'),
    (re.compile('Court of Criminal Appeals? of Tennessee', re.I), 'tenncrimapp'),

    (re.compile('Supreme Court of Texas', re.I), 'tex'),
    (re.compile('Commission of Appeals of Texas', re.I), 'tex'),
    (re.compile('Court of Appeals? of Texas', re.I), 'texapp'),
        # The Civil Appeals courts were renamed in 1985 to be the "Court of
        # Appeals"
        (re.compile('Court of Civil Appeals,? of (Beaumont, )?Texas', re.I), 'texapp'),
    (re.compile('Court of Criminal Appeals? of Texas', re.I), 'texcrimapp'),
    (re.compile('Special Court of Review', re.I), 'texreview'),
    (re.compile('Texas Judicial Panel on Multidistrict Litigation', re.I), 'texjpml'),

    (re.compile('Supreme Court of (the )?(state of )?Utah', re.I), 'utah'),
    (re.compile('Court of Appeals? (of )?Utah', re.I), 'utahctapp'),
    (re.compile('Utah Court of Appeals', re.I), 'utahctapp'),

    (re.compile('Supreme Court of Vermont', re.I), 'vt'),

    (re.compile('Supreme Court of Virginia', re.I), 'va'),
    (re.compile('Supreme Court of Appeals? of Virginia', re.I), 'va'),
    (re.compile('Court of Appeals? of Virginia', re.I), 'vactapp'),

    (re.compile('Supreme Court of Washington', re.I), 'wash'),
    (re.compile('Court of Appeals? of Washington', re.I), 'washctapp'),

    (re.compile('Supreme Court of( Appeals? of)?,? West Virginia', re.I), 'wva'),

    (re.compile('Supreme Court of Wisconsin', re.I), 'wis'),
    (re.compile('Court of Appeals? of (of )?Wisconsin', re.I), 'wisctapp'),
        (re.compile('Wisconsin Court of Appeals', re.I), 'wisctapp'),

    (re.compile('Supreme Court (of )?Wyoming', re.I), 'wyo'),

    # worker's compensation commissions
    (re.compile('Industrial Claim Appeals Office', re.I), 'coloworkcompcom'),
    (re.compile('Connecticut Compensation Review Board', re.I), 'connworkcompcom'),
    (re.compile('Commonwealth of Massachusetts Department of Industrial Accidents', re.I), 'maworkcompcom'),
    (re.compile('North Carolina Industrial Commission', re.I), 'ncworkcompcom'),
    (re.compile('Arkansas Workers\' Compensation Commission', re.I), 'arkworkcompcom'),
)

state_ag_pairs = (
    (re.compile('Attorney General of Arkansas', re.I), 'arkag'),
    (re.compile('Attorney General of California', re.I), 'calag'),
    (re.compile('Attorney General of Colorado', re.I), 'coloag'),
    (re.compile('Attorney General of Florida', re.I), 'flaag'),
    (re.compile('Attorney General of Kansas', re.I), 'kanag'),
    (re.compile('Attorney General of Louisiana', re.I), 'laag'),
    (re.compile('Attorney General of Maryland', re.I), 'mdag'),
    (re.compile('Attorney General of Missouri', re.I), 'moag'),
    (re.compile('Attorney General of Nebraska', re.I), 'nebag'),
    (re.compile('Attorney General of New York', re.I), 'nyag'),
    (re.compile('Attorney General of Oklahoma', re.I), 'oklaag'),
    (re.compile('Attorney General of Texas', re.I), 'texag'),
    (re.compile('Attorney General of Washington', re.I), 'washag'),
    (re.compile('Attorney General of Wisconsin', re.I), 'wisag'),
)

international_pairs = (
    (re.compile("Court of King's Bench", re.I), 'kingsbench'),
)


def match_court_string(court_str, federal_appeals=False,
                       federal_district=False, bankruptcy=False, state=False,
                       state_ag=False, international=False):
    """Look up a court string and return a CourtListener ID.

    Note you cannot use bankruptcy and federal_district together due to
    collisions between their regular expressions.

    :param court_str: The court string to look up.
    :param federal_appeals: Whether the string might be a federal appeals
    court.
    :param federal_district: Whether the string might be a federal district
    court. This may return abolished or specialty federal courts courts.
    :param bankruptcy: Whether the string might be a bankruptcy court. This may
    return abolished courts.
    :param state: Whether the string might be a state court.
    :param state_ag: Whether it might be a state AG "court".
    :param international: Whether it might be an international court.
    :returns The abbreviation for the court, if possible. Else, returns None
    """
    assert not (federal_district and bankruptcy), \
        "federal_district and bankruptcy cannot be used in conjunction"

    # Generally, we test these from most specific regex to least specific. The
    # order of the tests below should not be changed.
    matches = []
    if international:
        for regex, value in international_pairs:
            if re.search(regex, court_str):
                matches.append(value)
    if state:
        for regex, value in state_pairs:
            if re.search(regex, court_str):
                matches.append(value)
    if state_ag:
        for regex, value in state_ag_pairs:
            if re.search(regex, court_str):
                matches.append(value)
    if federal_appeals:
        for regex, value in ca_pairs:
            if re.search(regex, court_str):
                matches.append(value)
    if bankruptcy:
        for regex, value in fb_pairs:
            if re.search(regex, court_str):
                matches.append(value)
    # District go last because they've got some broad ones.
    if federal_district:
        for regex, value in fd_pairs:
            if re.search(regex, court_str):
                matches.append(value)

    # Safety check. If we have more than one match, that's a problem.
    assert len(matches) >= 1, "Too many matches for %s" % court_str
    return matches[0] if matches else None
