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
'''
import urllib2
import eyed3


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


def encode_audio(mime_type, data):
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
     - Convert wma to ogg: ffmpeg -i 03-4353RayvWarrenetal.wma -ar 22050 -ab 64k -ac 1 -acodec libvorbis 09-2661.new-ffmpeg.ogg
     - Convert mp3 to ogg: ffmpeg -i 09-2661.mp3 -ar 22050 -ab 64k -ac 1 -acodec libvorbis 09-2661.new-ffmpeg.ogg
     - Convert mp3 to mp3: ffmpeg -i 09-2661.mp3 -ar 22050 -ab 64k -ac 1 new-ffmpeg.mp3

    Sets meta data:
    ffmpeg -i in.avi -metadata title="my title" out.flv

    Returns an mp3 and an ogg of the file that are encoded properly.
    '''
    'avconv -i test_files/3.wma -ac 1 -ar 22050 3-mono-44100.mp3'

    return None


def set_meta_data(mp3_path, casename, court, year, argdate, docketNum, download_url):
    """
    Sets the meta data on the mp3 and ogg files as follows:
     - Title: Case name
     - Artist: Court name
     - Album: Supreme Court, 2009
     - Year: 2009
     - Comment: Argued: 2009-01-22. Docket num: 04-3329
     - Album Cover: CL Logo?

    Returns the two new and improved files.
    """
    audio_file = eyed3.load(mp3_path)
    audio_file.tag.clear()

    audio_file.tag.album = u'{court}, {year}'.format(court=court.full_name, year=year)
    audio_file.tag.artist = court.full_name
    audio_file.tag.artist_url = court.url
    audio_file.tag.audio_source_url = download_url
    audio_file.tag.comments = u'Argued: %s. Docket number: %s'.format(argdate, docketNum)
    audio_file.tag.genre = u'Speech'
    audio_file.tag.publisher = u'Free Law Project'
    audio_file.tag.publisher_url = u'http://www.freelawproject.org'
    audio_file.tag.recording_date = argdate
    audio_file.tag.title = casename

    # TODO Set the album cover to the court seal.

    audio_file.tag.save()



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
