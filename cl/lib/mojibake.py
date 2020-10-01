# -*- coding: utf-8 -*-

from django.utils.encoding import smart_str


def fix_mojibake(text):
    """Given corrupt text from pdffactory, converts it to sane text."""

    letter_map = {
        "¿": "a",
        "¾": "b",
        "½": "c",
        "¼": "d",
        "»": "e",
        "º": "f",
        "¹": "g",
        "¸": "h",
        "·": "i",
        "¶": "j",
        "μ": "k",
        "´": "l",
        "³": "m",
        "²": "n",
        "±": "o",
        "°": "p",
        "¯": "q",
        "®": "r",
        "-": "s",
        "¬": "t",
        "«": "u",
        "ª": "v",
        "©": "w",
        "¨": "x",
        "§": "y",
        "¦": "z",
        "ß": "A",
        "Þ": "B",
        "Ý": "C",
        "Ü": "D",
        "Û": "E",
        "Ú": "F",
        "Ù": "G",
        "Ø": "H",
        "×": "I",
        "Ö": "J",
        "Õ": "K",
        "Ô": "L",
        "Ó": "M",
        "Ò": "N",
        "Ñ": "O",
        "Ð": "P",
        "": "Q",  # Missing
        "Î": "R",
        "Í": "S",
        "Ì": "T",
        "Ë": "U",
        "Ê": "V",
        "É": "W",
        "": "X",  # Missing
        "Ç": "Y",
        "Æ": "Z",
        "ð": "0",
        "ï": "1",
        "î": "2",
        "í": "3",
        "ì": "4",
        "ë": "5",
        "ê": "6",
        "é": "7",
        "è": "8",
        "ç": "9",
        "ò": ".",
        "ô": ",",
        "æ": ":",
        "å": ";",
        "Ž": "'",
        "•": "'",  # s/b double quote, but identical to single.
        "Œ": "'",  # s/b double quote, but identical to single.
        "ó": "-",  # dash
        "Š": "-",  # n-dash
        "‰": "--",  # em-dash
        "ú": "&",
        "ö": "*",
        "ñ": "/",
        "÷": ")",
        "ø": "(",
        "Å": "[",
        "Ã": "]",
        "‹": "•",
    }

    plaintext = ""
    for letter in text:
        try:
            plaintext += letter_map[letter]
        except KeyError:
            try:
                plaintext += smart_str(letter)
            except UnicodeEncodeError:
                continue

    return plaintext
