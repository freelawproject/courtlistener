from django.http import Http404

# alphabet used for url encoding and decoding. Omits some letters, like O0l.
ALPHABET = "123456789abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"


def ascii_to_num(string, alphabet=ALPHABET):
    """Decode an ascii string back to the number it represents

    `string`: The string to decode
    """
    base = len(alphabet)
    strlen = len(string)
    num = 0
    i = 0
    try:
        for char in string:
            power = (strlen - (i + 1))
            num += alphabet.index(char) * (base ** power)
            i += 1
    except ValueError:
        # happens if letters like l, 1, o, 0 are used.
        raise Http404

    return num
