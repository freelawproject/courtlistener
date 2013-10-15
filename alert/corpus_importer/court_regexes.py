from math import ceil
import pickle
import re
import sys

fd_pairs = (
    (re.compile('D(\.|:|,|(ist(\.|(rict))))?,? (court )?(of )?Colu(m|(in))bia', re.I), 'dcd'),
    # 1820-1824 --> ALD
    (re.compile('M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Alabama', re.I), 'almd'),
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Alabama', re.I), 'alnd'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Alabama', re.I), 'alsd'),
    (re.compile('Alaska', re.I), 'akd'),
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Arizona', re.I), 'azd'),
    # 1836-1851 --> ARD
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Arkansas', re.I), 'ared'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Arkansas', re.I), 'arwd'),
    (re.compile('C(\.|(entral))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Cal(ifornia)?', re.I), 'cacd'),
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Cal(ifornia)?', re.I), 'cand'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Cal(ifornia)?', re.I), 'casd'),
    # No longer exists. Existed 1866-07-27 to 1886-08-05
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?California', re.I), 'californiad'),  # Must go last for Cal.
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Colo(rado)?', re.I), 'cod'),
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Conn', re.I), 'ctd'),
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Delaware', re.I), 'ded'),
    # 1845 to 1847 --> FLD
    (re.compile('M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Fl(orid)?a', re.I), 'flmd'),
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Fl(orid)?a', re.I), 'flnd'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Fl(orid)?a', re.I), 'flsd'),
    # 1789 to 1848 --> GAD
    (re.compile('M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?G(a|(eorgia))', re.I), 'gamd'),
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?G(a|(eorgia))', re.I), 'gand'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?G(a|(eorgia))', re.I), 'gasd'),
        (re.compile('Waycross Division', re.I), 'gasd'),
    (re.compile('Hawai', re.I), 'hid'),
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Idaho', re.I), 'idd'),
    # From 1819-1855 there existed a district of illinios court.
    # From 1855-1905 three existed northern and southern district courts.
    # From 1905-1978 there existed northern, eastern and southern district courts.
    # From 1978-present there exists northern, central and southern courts in Illinois.
    (re.compile('C(\.|(entral))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Ill(inois)?', re.I), 'ilcd'),
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Ill(inois)?', re.I), 'ilnd'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Illinois', re.I), 'ilsd'),
    # Abolished. 1905-03-03 to 1978-10-02
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Illinois', re.I), 'illinoised'),
    # Abolished. 1819-03-03 to 1855-02-13
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Illinois', re.I), 'illinoisd'), # Must go last
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Indiana', re.I), 'innd'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Indiana', re.I), 'insd'),
    # Abolished. 1817-03-03 to 1928-04-21
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Indiana', re.I), 'indianad'), # Must go last
    # 1845-1882 --> IAD
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Iowa', re.I), 'iand'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Iowa', re.I), 'iasd'),
    (re.compile('Kansas', re.I), 'ksd'),
    # 1789 to 1901 --> KYD
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Kentucky', re.I), 'kyed'),
    (re.compile('W(\.|(estern))? ?D(\.|:|(ist(\.|(rict)))),? ?(of )?Kentucky', re.I), 'kywd'),
    # 1812-1823 and 1866-1881 --> LAD
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Louisiana', re.I), 'laed'),
    (re.compile('Eastern District, Louisiana', re.I), 'laed'),
    (re.compile('M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Louisiana', re.I), 'lamd'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Louisiana', re.I), 'lawd'),
    (re.compile('D(\.|:|,|(istrict))? ?(of )?Maine', re.I), 'med'),
    (re.compile('D(\.|(istrict))? ?(of )?Maryland', re.I), 'mdd'),
        (re.compile(', Maryland', re.I), 'mdd'),
        (re.compile('Maryland Admiralty', re.I), 'mdd'),
    (re.compile('D?\.? ?(of )?Mass(achusetts)?', re.I), 'mad'),
    # 1836-1863 --> MID
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Michigan', re.I), 'mied'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Michigan', re.I), 'miwd'),
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Minn(\.|(esota))', re.I), 'mnd'),
    # 1818-1838 --> MSD
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Mississippi', re.I), 'msnd'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Mississippi', re.I), 'mssd'),
    # 1822-1857 --> MOD
    (re.compile('C(\.|(entral))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Missouri', re.I), 'mocd'),
    (re.compile('E(\.|(astern))? ?D(\.|(istrict))?,? ?(of )?(the )?Missouri', re.I), 'moed'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Missouri', re.I), 'mowd'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Missouri', re.I), 'mosd'),
        (re.compile('Missouri, W\.D', re.I), 'mowd'),
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Montana', re.I), 'mtd'),
    (re.compile('D(\.|(istrict))? ?(of )?Nebraska', re.I), 'ned'),
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Nevada', re.I), 'nvd'),
    (re.compile('New Hampshire', re.I), 'nhd'),
    # 1789-1801    --> NJD
    # 1801-1802    --> NJED and NJWD
    # 1802-present --> NJD
    (re.compile('New Jersey', re.I), 'njd'),
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?New Mexico', re.I), 'nmd'),
    # 1789-1814 --> NYD
    (re.compile('E(\.|(astern))? ?D(\.|(istrict)),? ?(of )?N(\.|(ew)) ?Y(ork)?', re.I), 'nyed'),
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?N(\.|(ew)) ?Y(ork)?', re.I), 'nynd'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?N(\.|(ew)) ?Y(ork)?', re.I), 'nysd'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?N(\.|(ew)) ?Y(ork)?', re.I), 'nywd'),
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
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?N(\.|(orth)) Car?olina', re.I), 'nced'),
    (re.compile('M(\.|(iddle))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?N(\.|(orth)) Car?olina', re.I), 'ncmd'),
        (re.compile('Greensboro Division', re.I), 'ncmd'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?N(\.|(orth)) Car?olina', re.I), 'ncwd'),
        (re.compile('Charlotte Division', re.I), 'ncwd'),
    (re.compile('North Dakota', re.I), 'ndd'),
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Ohio', re.I), 'ohnd'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Ohio', re.I), 'ohsd'),
    # Abolished. 1803-02-19 to 1855-02-10
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Ohio', re.I), 'ohiod'), # Must be the last court!
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Oklahoma', re.I), 'oked'),
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Oklahoma', re.I), 'oknd'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Oklahoma', re.I), 'okwd'),
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?Oregon', re.I), 'ord'),
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?P(a|(ennsylvania))', re.I), 'paed'),
    (re.compile('M(\.|(iddle))? ?D(\.|(ist\.))?,? ?(of )?P(a|(ennsylvania))', re.I), 'pamd'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?P(a|(ennsylvania))', re.I), 'pawd'),
    # Abolished. 1789-09-24 to 1818-04-20
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?P(a|(ennsylvania))', re.I), 'pennsylvaniad'),  # Must go last
    (re.compile('Rhode Island', re.I), 'rid'),
    # Abolished. 1823-02-21 to 1965-10-07
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?South Carolina', re.I), 'southcarolinaed'),
    # Abolished. 1823-02-21 to 1965-10-07
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?S(\.|(outh))? C(\.|(arolina))?', re.I), 'southcarolinawd'),
    (re.compile('D(\.|:|,|(ist(\.|(rict))))? ?(of )?S(\.|(outh))? C(\.|(arolina))?', re.I), 'scd'),  # Must go last!
    (re.compile('South Dakota', re.I), 'sdd'),
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Tenn(\.|(essee))', re.I), 'tned'),
    (re.compile('M(\.|(iddle))? ?D(\.|(istrict))?,? ?(of )?Tenn(\.|(essee))', re.I), 'tnmd'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Tenn(\.|(essee))', re.I), 'tnwd'),
    # Abolished. 1797-01-31 to 1839-06-18
    (re.compile('D(\.|(istrict))? ?(of )?Tennessee', re.I), 'tennessed'),  # Must be the last court!
    # 1845-1857 --> TXD
    # 1857-1879 --> TXED, TXWD
    # 1879-1902 --> TXED, TXWD, TXND
    # 1902-present --> TXED, TXWD, TXND, TXSD
    (re.compile('E ?(\.|(astern))? ?D ?(\.|:|(istrict)),? ?(of )?Tex(\.|(as))', re.I), 'txed'),
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Tex(\.|(as))', re.I), 'txnd'),
    (re.compile('S(\.|(outhern))? ?D(\.|(istrict)),? ?(of )?Texas', re.I), 'txsd'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Tex(\.|(as))', re.I), 'txwd'),
        (re.compile('Midland/Odessa', re.I), 'txwd'),
    (re.compile('Utah', re.I), 'utd'),
    (re.compile('Vermont', re.I), 'vtd'),
    # 1789-1801 --> VAD
    # 1801-1802 --> District of Virginia, District of Norfolk, District of Potomac
    # 1802-1819 --> VAD
    # 1819-1864 --> VAED, VAWD
    # 1864-1871 --> VAD
    # 1871-present --> VAWD, VAED
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict))))?,? ?(of )?Virginia', re.I), 'vaed'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Virginia', re.I), 'vawd'),
        (re.compile('Abingdon', re.I), 'vawd'),
        (re.compile('Big Stone Gap', re.I), 'vawd'),
        (re.compile('Lynchburg', re.I), 'vawd'),
    # 1890-1905 --> WAD
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Wash(ington)?', re.I), 'waed'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Wash(ington)?', re.I), 'wawd'),
    # 1864-1901 --> WVD
    (re.compile('N(\.|(orthern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?W(\.|(est)) V(a|(irginia))', re.I), 'wvnd'),
    (re.compile('S(\.|(outhern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?W(\.|(est)) V(a|(irginia))', re.I), 'wvsd'),
        (re.compile('West Virginia, at Charleston', re.I), 'wvsd'),
        (re.compile('Parkersburg Division', re.I), 'wvsd'),
    # 1848-1870 --> WID
    (re.compile('E(\.|(astern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Wisconsin', re.I), 'wied'),
        (re.compile('D\. Wisconsin, E\. D', re.I), 'wied'),
    (re.compile('W(\.|(estern))? ?D(\.|:|,|(ist(\.|(rict)))),? ?(of )?Wisconsin', re.I), 'wiwd'),
    (re.compile('Wyoming', re.I), 'wyd'),
    # Abolished. 1937-07-26 to 1982-03-31
    (re.compile('Canal Zone', re.I), 'canalzoned'),
    (re.compile('Guam', re.I), 'gud'),
    (re.compile('Northern Mariana', re.I), 'nmid'),
    (re.compile('Puerto Rico', re.I), 'prd'),
    (re.compile('Virgin Islands', re.I), 'vid'),
)

fb_pairs = (
    (re.compile('D(\.|(istrict)) of Columbia', re.I), 'dcb'),
    (re.compile('M(\.|(iddle))? ?D(\.|(istrict))? (of )?Alabama', re.I), 'almb'),
    (re.compile('N\.? ?D(\.|(istrict))? (of )?Alabama', re.I), 'alnb'),
    (re.compile('S\.? ?D(\.|(istrict))? (of )?Alabama', re.I), 'alsb'),
    (re.compile('D\. Alaska', re.I), 'akb'),
    (re.compile('D(\.|(istrict))? ?Arizona', re.I), 'arb'),
    (re.compile('E\.? ?D(\.|(istrict))? ?(of )?Arkansas', re.I), 'areb'),
    (re.compile('W\.? ?D(\.|(istrict))? ?(of )?Arkansas', re.I), 'arwb'),
    (re.compile('C\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', re.I), 'cacb'),
    (re.compile('E\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', re.I), 'caeb'),
    (re.compile('N\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', re.I), 'canb'),
    (re.compile('S\.? ?D(\.|(istrict))? ?(of )?Cal(ifornia)?', re.I), 'casb'),
    (re.compile('D(\.|(istrict)) ?(of )?Colorado', re.I), 'cob'),
    (re.compile('Connecticut', re.I), 'ctb'),
    (re.compile('D(\.|(istrict))? (of )?Delaware', re.I), 'deb'),
    (re.compile('M(\.|(iddle))? ?D(\.|(istrict))? ?(of )?Florida', re.I), 'flmb'),
        (re.compile('Florida, Tampa Division', re.I), 'flmb'),
        (re.compile('Florida, Jacksonville Division', re.I), 'flmb'),
    (re.compile('N(\.|(orthern))? ?D(\.|(istrict))? (of )?Florida', re.I), 'flnb'),
    (re.compile('S\. ?D(\.|(istrict))? (of )?Florida', re.I), 'flsb'),
    (re.compile('M\.? ?D(\.|(istrict))? (of )?Georgia', re.I), 'gamb'),
    (re.compile('N\.? ?D(\.|(istrict))? (of )?Georgia', re.I), 'ganb'),
        (re.compile('Atlanta Division', re.I), 'ganb'),
    (re.compile('S\. ?D(\.|(istrict))? Georgia', re.I), 'gasb'),
    (re.compile('D(\.|(istrict))? ?Hawai', re.I), 'hib'),
    (re.compile('D\. Idaho', re.I), 'idb'),
    (re.compile('C\.? ?D(\.|(istrict))? ?(of )?Ill(inois)?', re.I), 'ilcb'),
    (re.compile('N\.? ?D(\.|(istrict))? ?(of )?Ill(inois)?', re.I), 'ilnb'),
    (re.compile('S\.? ?D(\.|(istrict))? ?(of )?Ill(inois)?', re.I), 'ilsb'),
    (re.compile('N\.? ?D(\.|(istrict))? ?(of )?Indiana', re.I), 'innb'),
    (re.compile('S\.D\. (of )?Indiana', re.I), 'insb'),
    (re.compile('N\. ?D(\.|(istrict))? Iowa', re.I), 'ianb'),
    (re.compile('S\. ?D(\.|(istrict))? (of )?Iowa', re.I), 'iasb'),
    (re.compile('(D|M)(\.|(istrict)) (of )?Kan(sas)?', re.I), 'ksb'),
    (re.compile('E\.? ?D(\.|(istrict))? (of )?Kentucky', re.I), 'kyeb'),
    (re.compile('W\.? ?D(\.|(istrict))? (of )?Kentucky', re.I), 'kywb'),
    (re.compile('E\.? ?D(\.|(istrict))? (of )?Loui?siana', re.I), 'laeb'),
        (re.compile('Eastern District, Louisiana', re.I), 'laeb'),
    (re.compile('M\.? ?D(\.|(istrict))? (of )?Loui?siana', re.I), 'lamb'),
    (re.compile('W\.? ?D(\.|(istrict))? (of )?Loui?siana', re.I), 'lawb'),
    (re.compile('D. Maine', re.I), 'meb'),
    (re.compile('Maryland', re.I), 'mdb'),
    (re.compile('D(\.|(istrict))? ?(of )?Mass', re.I), 'mab'),
        (re.compile(', Massachusetts', re.I), 'mab'),
    (re.compile('E\.? ?D(\.|(istrict))? (of )?Michigan', re.I), 'mieb'),
    (re.compile('W\.D(\.|(istrict))? (of )?Michigan', re.I), 'miwb'),
    (re.compile('D(\.|(istrict))? ?Minnesota', re.I), 'mnb'),
    (re.compile('N\.? ?D(\.|(istrict))? (of )?Mississippi', re.I), 'msnb'),
    (re.compile('S\.? ?D(\.|(istrict))? (of )?Mississippi', re.I), 'mssb'),
    (re.compile('E\.? ?D(\.|(istrict))? ?(of )?Missouri', re.I), 'moeb'),
    (re.compile('W\.? ?D(\.|(istrict))? ?(of )?Missouri', re.I), 'mowb'),
    (re.compile('D\. Montana', re.I), 'mtb'),
    # Here we avoid a conflict with state abbreviations
    (re.compile('D(\.|(istrict))? (of )?Neb(raska)?', re.I), 'nebraskab'),
    (re.compile('Nevada', re.I), 'nvb'),
    (re.compile('New Hampshire', re.I), 'nhb'),
        (re.compile('D\.N\.H', re.I), 'nhb'),
    (re.compile('D(\.|(istrict))? ?New Jersey', re.I), 'njb'),
        (re.compile(', New Jersey', re.I), 'njb'),
    (re.compile('New Mexico', re.I), 'nmb'),
        (re.compile('State of New Mexico', re.I), 'nmb'),
    (re.compile('E\.? ?D(\.|(istrict))? (of )?New York', re.I), 'nyeb'),
        (re.compile('E\.D\.N\.Y', re.I), 'nyeb'),
    (re.compile('N\.? ?D(\.|(istrict))? (of )?New York', re.I), 'nynb'),
    (re.compile('S\. ?D(\.|(istrict))? (of )?New York', re.I), 'nysb'),
        (re.compile('Southern District of New York', re.I), 'nysb'),
        (re.compile('S.D.N.Y', re.I), 'nysb'),
    (re.compile('W\.? ?D(\.|(istrict))? (of )?New York', re.I), 'nywb'),
    (re.compile('E\.? ?D(\.|(istrict))? (of )?North Carolina', re.I), 'nceb'),
    (re.compile('M\.? ?D(\.|(istrict))? (of )?North Carolina', re.I), 'ncmb'),
    (re.compile('W\.? ?D(\.|(istrict))? (of )?North Carolina', re.I), 'ncwb'),
    (re.compile('North Dakota', re.I), 'ndb'),
    (re.compile('N\.? ?D(\.|(istrict))? (of )?Ohio', re.I), 'ohnb'),
        (re.compile('Northern District of Ohio', re.I), 'ohnb'),
    (re.compile('S\. ?D(\.|(istrict))? (of )?Ohio', re.I), 'ohsb'),
    (re.compile('E\.? ?D(\.|(istrict))? (of )?Oklahoma', re.I), 'okeb'),
    (re.compile('N\.? ?D(\.|(istrict))? (of )?Oklahoma', re.I), 'oknb'),
    (re.compile('W\.? ?D(\.|(istrict))? (of )?Oklahoma', re.I), 'okwb'),
    (re.compile('Oregon', re.I), 'orb'),
    (re.compile('E\.? ?D(\.|(istrict))? (of )?Pennsylvania', re.I), 'paeb'),
    (re.compile('M\.? ?D(\.|(istrict))? (of )?Pennsylvania', re.I), 'pamb'),
    (re.compile('W\.? ?D(\.|(istrict))? (of )?Pennsylvania', re.I), 'pawb'),
    (re.compile('D(\.|(istrict))? ?Rhode Island', re.I), 'rib'),
        (re.compile(', Rhode Island', re.I), 'rib'),
        (re.compile(', D\.R\.I', re.I), 'rib'),
    (re.compile('D(\.|(istrict))? ?(of )?South Carolina', re.I), 'scb'),
        (re.compile('D\.S\.C', re.I), 'scb'),
    (re.compile('D\. South Dakota', re.I), 'sdb'),
        (re.compile(', South Dakota', re.I), 'sdb'),
    (re.compile('E\.? ?D(\.|(istrict))? (of )?Te(r|n)n(essee)?', re.I), 'tneb'),
    (re.compile('M\.? ?D(\.|(istrict))? (of )?Tenn(essee)?', re.I), 'tnmb'),
        (re.compile('Middle District of Tennessee', re.I), 'tnmb'),
        (re.compile('M\.D\.S\. Tennessee', re.I), 'tnmb'),
        (re.compile('Nashville', re.I), 'tnmb'),
    (re.compile('W\.? ?D(\.|(istrict))? (of )?Tennessee', re.I), 'tnwb'),
    (re.compile('D. Tennessee', re.I), 'tennesseeb'),
    (re.compile('E\.? ?D ?(\.|(istrict))? (of )?Texas', re.I), 'txeb'),
    (re.compile('N\.? ?D(\.|(istrict))? (of )?Texas', re.I), 'txnb'),
    (re.compile('S\.? ?D(\.|(istrict))? (of )?Texas', re.I), 'txsb'),
    (re.compile('W\.? ?D(\.|(istrict))? (of )?Texas', re.I), 'txwb'),
    (re.compile('Utah', re.I), 'utb'),
    (re.compile('D(\.|(istrict))? ?(of )?Vermont', re.I), 'vtb'),
    (re.compile('E\.? ?D(\.|(istrict))?,? ?(of )?Virginia', re.I), 'vaeb'),
    (re.compile('W\.? ?D(\.|(istrict))?,? ?(of )?Virginia', re.I), 'vawb'),
        (re.compile('Big Stone Gap', re.I), 'vawb'),
    (re.compile('E\.? ?D(\.|(istrict))? (of )?Washington', re.I), 'waeb'),
    (re.compile('W\.? ?D(\.|(istrict))? (of )?Washington', re.I), 'wawb'),
    (re.compile('N\.? ?D(\.|(istrict))? (of )?W(\.|(est)) Virginia', re.I), 'wvnb'),
    (re.compile('S\.? ?D(\.|(istrict))? (of )?W(\.|(est)) Virginia', re.I), 'wvsb'),
    (re.compile('E\.? ?D(\.|(istrict))? (of )?Wis(consin)?', re.I), 'wieb'),
    (re.compile('W(\.|(estern))? ?D(\.|(istrict))? (of )?Wis(consin)?', re.I), 'wiwb'),
    (re.compile('D\. Wyoming', re.I), 'wyb'),

    # Bankruptcy special
    (re.compile('Guam', re.I), 'gub'),
    (re.compile('Northern Mariana', re.I), 'nmib'),
    (re.compile('Puerto Rico', re.I), 'prb'),
    (re.compile('Virgin Islands', re.I), 'vib'),
)

state_pairs = (
    (re.compile('D((istrict)|\.) (of )?C((olumbia)|\.) Court of Appeals', re.I), 'dc'),
        (re.compile('D((istrict)|\.) (of )?C((olumbia)|\.) Municipal Court of Appeals', re.I), 'dc'),
            (re.compile('Municipal Court of Appeals? (for the )?D((istrict)|\.) (of )?C((olumbia)|\.)', re.I), 'dc'),
        (re.compile('Supreme Court of the D((istrict)|\.) (of )?C((olumbia)|\.)', re.I), 'dc'),
    (re.compile('Supreme Court of Alabama', re.I), 'ala'),
    (re.compile('Court of Criminal Appeals? of Alabama', re.I), 'alacrimapp'),
        (re.compile('Alabama Court of Criminal Appeals?', re.I), 'alacrimapp'),
    (re.compile('Court of Civil Appeals? of Alabama', re.I), 'alacivapp'),
    (re.compile('Court of Appeals? of Alabama', re.I), 'alactapp'),
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
    (re.compile('Supreme Court of Colorado', re.I), 'colo'),
    (re.compile('Colorado Court of Appeals', re.I), 'coloctapp'),
        (re.compile('Court of Appeals? of Colorado', re.I), 'coloctapp'),
    (re.compile('Supreme Court of Connecticut', re.I), 'conn'),
    (re.compile('Appellate Court of Connecticut', re.I), 'connappct'),
    (re.compile('Superior Court of Connecticut', re.I), 'connsuperct'),
    (re.compile('Supreme Court of (the State of )?Delaware', re.I), 'del'),
        (re.compile('Delaware Supreme Court', re.I), 'del'),
    (re.compile('Court of Chancery of (the State of )?Delaware', re.I), 'delch'),
        (re.compile('Chancery Court of Delaware', re.I), 'delch'),
    (re.compile('Superior Court of (the State of )?Delaware', re.I), 'delsuperct'),
        # These two merged into the Superior court of Delaware
        (re.compile('Orphans\'? Court of Delaware', re.I), 'delsuperct'),
        (re.compile('Court of General Sessions', re.I), 'delsuperct'),
        (re.compile('Court of Oyer and Terminer of Delaware', re.I), 'delsuperct'),
    (re.compile('Family Court of Delaware', re.I), 'delfamct'),
    (re.compile('Supreme Court of Florida', re.I), 'fla'),
    (re.compile('District Courts? of Appeal (of )?Florida', re.I), 'fladistctapp'),
    (re.compile('Supreme Court of Georgia', re.I), 'ga'),
    (re.compile('Court of Appeals? of Georgia', re.I), 'gactapp'),
    (re.compile('Supreme Court of Illinois', re.I), 'ill'),
    (re.compile('Supreme Court of Hawai', re.I), 'haw'),
    (re.compile('Intermediate Court (of )?Appeals? .*Hawai', re.I), 'hawapp'),
        (re.compile('Court of Appeals? of Hawai', re.I), 'hawapp'),
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
    (re.compile('Supreme Judicial Court of Maine', re.I), 'me'),
    (re.compile('Court of Appeals? of Maryland', re.I), 'md'),
        (re.compile('Supreme Court of Maryland', re.I), 'md'),
    (re.compile('Court of Special Appeals? of Maryland', re.I), 'mdctspecapp'),
    (re.compile('Supreme (Judicial )?Court of Massachusetts', re.I), 'mass'),
    (re.compile('Appeals? Court of Massachusetts', re.I), 'massappct'),
    (re.compile('Supreme Court of Michigan', re.I), 'mich'),
    (re.compile('Michigan Court of Appeals', re.I), 'michctapp'),
        (re.compile('Court of Appeals? of Michigan', re.I), 'michctapp'),
    (re.compile('Supreme Court of Minnesota', re.I), 'minn'),
    (re.compile('Court of Appeals? of Minnesota', re.I), 'minnctapp'),
    (re.compile('Supreme Court of Mississippi', re.I), 'miss'),
    (re.compile('Court of Appeals? of Mississippi', re.I), 'missctapp'),
    (re.compile('Supreme Court of Missouri', re.I), 'mo'),
    (re.compile('Missouri Court of Appeals', re.I), 'moctapp'),
        (re.compile('St\. Louis,? Court of Appeals', re.I), 'moctapp'),
        (re.compile('Kansas City.? Court of appeals', re.I), 'moctapp'),
        (re.compile('Springfield,? Court of appeals', re.I), 'moctapp'),
    (re.compile('Supreme Court of Montana', re.I), 'mont'),
    (re.compile('Supreme Court of Nebraska', re.I), 'neb'),
    (re.compile('Court of Appeals? of Nebraska', re.I), 'nebctapp'),
        (re.compile('Nebraska Court of Appeals', re.I), 'nebctapp'),
    (re.compile('Supreme Court of Nevada', re.I), 'nev'),
    (re.compile('Supreme Court of New Hampshire', re.I), 'nh'),
    (re.compile('Supreme Court of New Jersey', re.I), 'nj'),
    (re.compile('Superior Court of New Jersey', re.I), 'njsuperctappdiv'),
    (re.compile('Tax Court of New Jersey', re.I), 'njtaxct'),
    (re.compile('Supreme Court of New Mexico', re.I), 'nm'),
    (re.compile('Court of Appeals? of New Mexico', re.I), 'nmctapp'),
        (re.compile('New Mexico Court of Appeals', re.I), 'nmctapp'),
    (re.compile('Court of Appeals? of (the State of )?New York', re.I), 'ny'),
    (re.compile('Appellate Division of the Supreme Court of the State of New York', re.I), 'nyappdiv'),
        (re.compile('Supreme Court, Albany County', re.I), 'nyappdiv'),
        (re.compile('Supreme Court.*New York County', re.I), 'nyappdiv'),
        (re.compile('Supreme Court.*Kings County', re.I), 'nyappdiv'),
    (re.compile('Surrogate\'s Court', re.I), 'surct'),
    (re.compile('Supreme Court of North Carolina', re.I), 'nc'),
    (re.compile('Court of Appeals? (of )?North Carolina', re.I), 'ncctapp'),
        (re.compile('North Carolina Court of Appeals', re.I), 'ncctapp'),
    (re.compile('Supreme Court of North Dakota', re.I), 'nd'),
    (re.compile('Court of Appeals? of North Dakota', re.I), 'ndctapp'),
    (re.compile('Supreme Court of Ohio', re.I), 'ohio'),
    (re.compile('Supreme Court (of )?Oklahoma', re.I), 'okla'),
    (re.compile('Court of Criminal Appeals? (of )?Oklahoma', re.I), 'oklacrimapp'),
        (re.compile('Criminal Courts of Appeals? of Oklahoma', re.I), 'oklacrimapp'),
    (re.compile('Court of Civils? Appeals? of Oklahoma', re.I), 'oklacivapp'),
        # When they refer to simply the "Court of Appeals" they mean the the civil court
        (re.compile('Court of Appeals?,? (civil )?(of )?(State )?(of )?Oklahoma', re.I), 'oklacivapp'),
    (re.compile('Oklahoma Judicial Ethics Advisory Panel', re.I), 'oklajeap'),
    (re.compile('Court on the Judiciary of Oklahoma', re.I), 'oklacoj'),
    (re.compile('Supreme Court (((for)|(of)) the State )?of (the )?Oregon', re.I), 'or'),
        (re.compile('Oregon Supreme Court', re.I), 'or'),
    (re.compile('Court of Appeals? of (the )?(state of )?Oregon', re.I), 'orctapp'),
        (re.compile('oregon court of appeals', re.I), 'orctapp'),
    (re.compile('Supreme Court of Pennsylvania', re.I), 'pa'),
    (re.compile('Superior Court of Pennsylvania', re.I), 'pasuperct'),
    (re.compile('Commonwealth Court of Pennsylvania', re.I), 'pacommwct'),
    (re.compile('Court of Judicial Discipline of Pennsylvania', re.I), 'cjdpa'),
    (re.compile('Supreme Court,? of Rhode Island', re.I), 'ri'),
    (re.compile('Supreme Court of South Carolina', re.I), 'sc'),
    (re.compile('Court of Appeals? of South Carolina', re.I), 'scctapp'),
    (re.compile('Supreme Court of South Dakota', re.I), 'sd'),
    (re.compile('Supreme Court of Tennessee', re.I), 'tenn'),
    (re.compile('Court of Appeals? (of )?Tennessee', re.I), 'tennctapp'),
        (re.compile('Tennessee Court of Appeals', re.I), 'tennctapp'),
    (re.compile('Court of Criminal Appeals? of Tennessee', re.I), 'tenncrimapp'),
    (re.compile('Supreme Court of Texas', re.I), 'tex'),
    (re.compile('Court of Appeals? of Texas', re.I), 'texapp'),
        # The Civil Appeals courts were renamed in 1985 to be the "Court of Appeals"
        (re.compile('Court of Civil Appeals,? of (Beaumont, )?Texas', re.I), 'texapp'),
    (re.compile('Court of Criminal Appeals? of Texas', re.I), 'texcrimapp'),
    (re.compile('Special Court of Review', re.I), 'texreview'),
    (re.compile('Supreme Court of (the )?(state of )?Utah', re.I), 'utah'),
    (re.compile('Court of Appeals? (of )?Utah', re.I), 'utahctapp'),
    (re.compile('Utah Court of Appeals', re.I), 'utahctapp'),
    (re.compile('Supreme Court of Vermont', re.I), 'vt'),
    (re.compile('Supreme Court of Virginia', re.I), 'va'),
    (re.compile('Court of Appeals? of Virginia', re.I), 'vactapp'),
    (re.compile('Supreme Court of Washington', re.I), 'wash'),
    (re.compile('Court of Appeals? of Washington', re.I), 'washctapp'),
    (re.compile('Supreme Court of( Appeals? of)?,? West Virginia', re.I), 'wva'),
    (re.compile('Supreme Court of Wisconsin', re.I), 'wis'),
    (re.compile('Court of Appeals? of (of )?Wisconsin', re.I), 'wisctapp'),
        (re.compile('Wisconsin Court of Appeals', re.I), 'wisctapp'),
    (re.compile('Supreme Court (of )?Wyoming', re.I), 'wyo'),
)


##########################################
# This variable is used to do statistical work on Opinions whose jurisdiction is unclear. The problem is that
# many Opinions, probably thousands of them, have a court like, "D. Wisconsin." Well, Wisconsin has an east and
# west district, but no generic district, so this has to be resolved. When we hit such a case, we set it aside
# for later processing, once we've processed all the easy cases. At that point, we will have the variable below,
# judge stats, which will have all of the judges along with a count of their jurisdictions:
# judge_stats = {
#     'McKensey': {
#         'wied': 998,
#         'wis': 2
#     }
# }
# So in this case, you can see quite clearly that McKensey is a judge at wied, and we can classify the case as
# such.
##########################################
try:
    with open('judge_stats.pkl', 'rb') as fix_file:
        judge_stats = pickle.load(fix_file)
except (IOError, EOFError):
    print "Unable to load judge_stats.pkl"
    sys.exit(1)


def disambiguate_by_judge(judge, threshold=0.85):
    """Using the judge found in the document and the judges found across the entire corpus, determine the court where
    the judge works more than `threshold` percent of the time."""
    try:
        judge_dict = judge_stats[judge]
    except KeyError:
        return None

    total_cases_judge_heard = 0
    for v in judge_dict.values():
        total_cases_judge_heard += v

    # Is one of the courts more than `threshold` common?
    threshold_count = ceil(threshold * total_cases_judge_heard)
    possible_courts = []
    for court, count in judge_dict.iteritems():
        if count >= threshold_count:
            possible_courts.append(court)

    if len(possible_courts) == 1:
        return possible_courts[0]
    else:
        # Alas, sustained ambiguity!
        return None


