import datetime
from distutils.spawn import find_executable

from django.utils.text import slugify

from cl.audio.models import Audio


def get_audio_binary() -> str:
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
    path_to_binary = find_executable("avconv")
    if path_to_binary is None:
        path_to_binary = find_executable("ffmpeg")
        if path_to_binary is None:
            raise Exception(
                "Unable to find avconv or ffmpeg for doing "
                "audio conversions."
            )
    return path_to_binary


def make_af_filename(
    court_id: str,
    docket_number: str,
    date_argued: datetime.date,
    extension: str,
) -> str:
    """Make a filename for the audio file for uploading to IA"""
    parts = [
        "gov",
        "uscourts",
        court_id,
        slugify(docket_number),
        date_argued.isoformat(),
        extension,
    ]
    return ".".join(parts)


def transcription_was_hallucinated(audio: Audio) -> bool:
    """Detects when a phrase is repeated many times in the audio,
    due to a transcription error by Whisper, known as "hallucination"

    We use the relationship between audio duration and number of
    unique words. The relationship is linear and very stable,
    If the particular instance does not conform, we will tag it
    as a hallucination. Check the tests for examples

    There may be other types of hallucinations that will require
    other approaches
    """
    # we don't have much audios in this range, the model does
    # not work well here
    if not audio.duration or audio.duration < 500:
        return False

    # Parameters got from a linear model estimated
    # from 1377 transcriptions
    # lm(unique_words ~ duration)
    intercept, linear_coef = 376, 0.435
    tolerance = 0.5

    unique_words = len(set(audio.stt_transcript.split(" ")))
    expected_number_of_unique_words = intercept + linear_coef * audio.duration

    # Accepts a variation up to 50% less from the line of best fit
    if unique_words > expected_number_of_unique_words * tolerance:
        return False

    return True
