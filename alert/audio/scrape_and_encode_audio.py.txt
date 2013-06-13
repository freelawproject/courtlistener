'''
    This is some complicated stuff. The basic process is as follows:
     - Go to the court site, identify the audio file
     - Encode it properly as mono mp3 and mono ogg
     - Update ID3 information for mp3, and header info for ogg.
     - Update the DB to link to it from the documents page, save it to DB

    Some notes:
     - Oyez does a good job with id3 information:
        - Title: Case name
        - Artist: Court name
        - Album: Supreme Court 2009 Term
        - Year: 2009
        - Comment: 2009 Term (Docket No. 08-861)
        - Album Cover: CL Logo?
     - Audio conversions:
        - Update ID3 tags
        - Convert to mono
        - Convert to a reasonable sample rate/bitrate combo
     - UI notes:
        - Need RSS feeds for audio
        - Coverage page needs to be updated
        - UI hooks on each page, with rewrite of pages so they look right when we only have audio for a case.

    Court notes:
     - First Circuit:
        - RSS: http://www.ca1.uscourts.gov/files/audio/audiorss.php
        - mp3
        - meta: case name, docket num, arg date
     - Second Circuit:
        - None
     - Third Circuit:
        - Last seven days: http://www.ca3.uscourts.gov/oralargument/ListArguments7.aspx
        - All: http://www.ca3.uscourts.gov/oralargument/ListArgumentsAll.aspx (can be chron sorted)
        - wma
        - meta: case name, docket num, arg date
     - Fourth Circuit:
        - None
     - Fifth Circuit:
        - http://www.ca5.uscourts.gov/OralArgumentRecordings.aspx (use date fields to return all oral args)
        - http://www.ca5.uscourts.gov/Rss.aspx?Feed=OralArgRecs (Feed of args)
        - wma
        - meta: case name, docket num, arg date, appearing attorneys
     - Sixth Circuit
        - None
     - Seventh Circuit
        - RSS: http://www.ca7.uscourts.gov/fdocs/docs.fwx?submit=rss_args
        - Also available via POST at http://www.ca7.uscourts.gov/fdocs/docs.fwx (submit 10 for all 2010 cases, etc.)
        - Audio is at: http://www.ca7.uscourts.gov/fdocs/docs.fwx?submit=showbr&shofile=10-2056_001.mp3
        - mp3
        - meta (RSS): case name, docket num, case type
        - meta (HTML): case name, docket num, more on linked page.
     - Eighth Circuit:
        - RSS: http://8cc-www.ca8.uscourts.gov/circ8rss.xml (reverse order?)
        - mp3
        - meta: case name, docket num, arg date
     - Ninth Circuit:
        - Cases are here: http://www.ca9.uscourts.gov/media/ (can be sorted)
        - Links take the form: http://www.ca9.uscourts.gov/datastore/media/2010/10/13/08-16436.wma
        - mp3
        - meta: case name, docket num, arg date
     - Tenth Circuit:
        -None
     - Eleventh Circuit:
        - None
     - DC Circuit:
        - Denied.
     - Fed. Circuit:
        - RSS with ALL cases back to 2009-01: http://www.cafc.uscourts.gov/rss-audio-recordings.php
        - Also available via search queries
        - mp3
        - meta: case name, docket num, date (?)
     - SCOTUS:
        - Latest from here: http://www.supremecourt.gov/oral_arguments/argument_audio.aspx
        - Old from Oyez
        - mp3, wma, ra
        - meta: case name, docket num, arg date

    Counts:
     - 1st: Latest only
     - 2nd: None
     - 3rd: 574
     - 4th: None
     - 5th: 236
     - 6th: None
     - 7th: (2010: 136, 2009: 905, 2008: 1165, 2007: 1122, 2006: 1260,
             2005: 1317, 2004: 1005, 2003: 933, 2002: 864, 2001: 806,
             2000: 661, 1999: 576, 1998: 134, 1997: 20, 1996: 3, 1995: 1,
             1994: 1, 1993: 1, 1992: 0)
             TOTAL: ~10,000 cases, most lack audio...maybe 3,000 with audio.
     - 8th: Latest only.
     - 9th: ~6000
     - D.C.: Denied
     - Fed: 2152
     - Scotus: Latest plus Oyez.
     - GRAND TOTAL: 11962
     - SIZE, AT 20MB/ARG: 233GB.
'''


def makeAudioFromUrl(url, audioLink):
    '''
    Using a URL, downloads the file at the other end.

    Returns a StringIO of the audio file, an Audio object, a boolean
    indicating whether the Audio file was created or pulled from the DB, and
    a boolean indicating if there were any errors.
    '''

    # Intelligently fixes relative links and problems of that sort.
    url = urljoin(url, audioLink)

    # get the audio file!
    try:
        webFile = urllib2.urlopen(url)
        stringThing = StringIO.StringIO()
        stringThing.write(webFile.read())
        myFile = ContentFile(stringThing.getvalue())
        webFile.close()
    except:
        print "ERROR DOWNLOADING FILE!: " + str(LinkToPdf)
        error = True
        return "ERROR", "DOWNLOADING", "FILE", error

    # make the SHA1
    data = myFile.read()
    sha1Hash = hashlib.sha1(data).hexdigest()

    # using that, we check for a dup
    audio, created = Audio.objects.get_or_create(SHA1=sha1Hash)

    if created:
        # we only do this if it's new
        audio.sha1 = sha1Hash
        audio.download_URL = url

    error = False

    return myFile, audio, created, error


def encode_audio(mime - type, data):
    '''
    Fires off a new thread that does the audio encoding for the file. If
    possible, uses a low nice value when doing encoding.

    Currently handles wma or mp3.

    Adds ffmpeg and libavcodec-extra-52 as dependencies....and they need to be
    installed from source b/c ubuntu sucks it up on keeping these up to date.
    Follow these instructions, but remember to install lame as well:
    http://ubuntuforums.org/showpost.php?p=9868359&postcount=1289

    Convert to 22050 sample rate, mono, 64kps bitrate:
     -ar 22050 -ab 64k -ac 1 out.mp3
     -ar 22050 -ab 64k -ac 1 -acodec libvorbis out.ogg

    Commands that work:
     - Convert wma to ogg: ffmpeg -i 03-4353RayvWarrenetal.wma -metadata Artist="Artist name" -metadata Title="Case name" -metadata Album="Supreme court 2009 term" -metadata Year="2009" -metadata Comment="Docket number: 09-2661" -ar 22050 -ab 64k -ac 1 -acodec libvorbis 09-2661.new-ffmpeg.ogg
     - Convert mp3 to ogg: ffmpeg -i 09-2661.mp3 -metadata Artist="Artist name" -metadata Title="Case name" -metadata Album="Supreme court 2009 term" -metadata Year="2009" -metadata Comment="Docket number: 09-2661" -ar 22050 -ab 64k -ac 1 -acodec libvorbis 09-2661.new-ffmpeg.ogg
     - Convert mp3 to mp3: ffmpeg -i 09-2661.mp3 -metadata Artist="Artist name" -metadata Title="Case name" -metadata Album="Supreme court 2009 term" -metadata Year="2009" -metadata Comment="Docket number: 09-2661" -ar 22050 -ab 64k -ac 1 new-ffmpeg.mp3

    Sets meta data:
    ffmpeg -i in.avi -metadata title="my title" out.flv

    Returns an mp3 and an ogg of the file that are encoded properly.
    '''
    # This might indicate how to set the nice value of this process:
    # http://stackoverflow.com/questions/2463533/is-it-possible-to-renice-a-subprocess
    # A better method is probably using a preexec_fn of os.nice() to the
    # subprocess call.
    if mime - type == "mp3":
        # Convert the sample rate to something good, make it mono.
    elif mime - type == "wma":
        # Convert make an acceptable mp3 from the wma.

    # make the ogg from the mp3.

    # add id3 data to the mp3

    # add meta data to the ogg

    return

def set_meta_data(mp3, ogg, casename, court, year, argdate, docketNum):
    '''
    Sets the meta data on the mp3 and ogg files as follows:
     - Title: Case name
     - Artist: Court name
     - Album: Supreme Court, 2009
     - Year: 2009
     - Comment: Argued: 2009-01-22. Docket num: 04-3329
     - Album Cover: CL Logo?

    Returns the two new and improved files.
    '''


def scrapeCourt(courtID):
    if VERBOSITY >= 1: RESULT += "NOW SCRAPING COURT: " + str(courtID) + "\n"
    if VERBOSITY >= 2: print "NOW SCRAPING COURT: " + str(courtID)

    if (courtID == 1):
        """
        Audio is available from the first circuit if you go to their RSS feed.
        So go to their RSS feed we shall.
        """

        url = "http://www.ca1.uscourts.gov/files/audio/audiorss.php"
        try: html = urllib2.urlopen(url).read()
        except urllib2.HTTPError:
            RESULT += "***ERROR CONNECTING TO COURT: " + str(courtID) + "***\n"

        if DAEMONMODE:
            changed = courtChanged(url, html)
            if not changed:
                # if the court hasn't changed, punt.
                return

        # gets rid of errant ampersands, making the XML valid.
        punctuationRegex = re.compile(" & ")
        html = re.sub(punctuationRegex, " &amp; ", html)
        tree = etree.fromstring(html)

        '''
        Process:
         - Get the URL of the audio file, and hand that to makeAudioFromUrl
         - Hand the audio file to encode_audio to make the mp3 and ogg files
         - Figure out the case name, court, year, argdate and docketNum
            - hand all that to the set_meta_data function.
         - See if a document can be linked up with the audio file.
         - Save everything.
        '''
