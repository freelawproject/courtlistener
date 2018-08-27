from distutils.spawn import find_executable


def get_audio_binary():
    """Get the path to the installed binary for doing audio conversions

    Ah, Linux. Land where ffmpeg can fork into avconv, where avconv can be the
    correct binary for years and years, and where much later, the fork can be
    merged again and avconv can disappear.

    Yes, the above is what happened, and yes, avconv and ffmpeg are pretty much
    API compatible despite forking and them merging back together. From the
    outside, this appears to be an entirely worthless fork that they embarked
    upon, but what do we know.

    In any case, this program finds whichever one is available and then
    provides it to the user. ffmpeg was the winner of the above history, but we
    stick with avconv as our default because it was the one that was winning
    when we originally wrote our code. One day, we'll want to switch to ffmpeg,
    once avconv is but dust in the bin of history.

    :returns path to the winning binary
    """
    path_to_binary = find_executable('avconv')
    if path_to_binary is None:
        path_to_binary = find_executable('ffmpeg')
        if path_to_binary is None:
            raise Exception("Unable to find avconv or ffmpeg for doing "
                            "audio conversions.")
    return path_to_binary


def make_af_filename(court_id, docket_number, date_argued, extension):
    """Make a filename for the audio file for uploading to IA"""
    return '.'.join(['gov', 'uscourts', court_id, docket_number,
                     date_argued.isoformat(), extension])
