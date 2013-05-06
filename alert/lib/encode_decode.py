from django.http import Http404

# alphabet used for url encoding and decoding. Omits some letters, like O0l1.
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


def num_to_ascii(num, alphabet=ALPHABET):
    """Encode a number in Base X

    `num`: The number to encode
    """
    if (num <= 0):
        return alphabet[0]
    arr = []
    base = len(alphabet)
    while num:
        rem = num % base
        num = num // base
        arr.append(alphabet[rem])
    arr.reverse()
    return ''.join(arr)
