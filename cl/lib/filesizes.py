def convert_size_to_bytes(size_str: str) -> int:
    """Convert human filesizes to bytes.

    Special cases:
     - singular units, e.g., "1 byte"
     - byte vs b
     - yottabytes, zetabytes, etc.
     - with & without spaces between & around units.
     - floats ("5.2 mb")

    To reverse this, see hurry.filesize or the Django filesizeformat template
    filter.

    :param size_str: A human-readable string representing a file size, e.g.,
    "22 megabytes".
    :return: The number of bytes represented by the string.
    """
    multipliers = {
        "kilobyte": 1024,
        "megabyte": 1024**2,
        "gigabyte": 1024**3,
        "terabyte": 1024**4,
        "petabyte": 1024**5,
        "exabyte": 1024**6,
        "zetabyte": 1024**7,
        "yottabyte": 1024**8,
        "kb": 1024,
        "mb": 1024**2,
        "gb": 1024**3,
        "tb": 1024**4,
        "pb": 1024**5,
        "eb": 1024**6,
        "zb": 1024**7,
        "yb": 1024**8,
    }

    for suffix in multipliers:
        size_str = size_str.lower().strip().strip("s")
        if size_str.lower().endswith(suffix):
            return int(float(size_str[0 : -len(suffix)]) * multipliers[suffix])
    else:
        if size_str.endswith("b"):
            size_str = size_str[0:-1]
        elif size_str.endswith("byte"):
            size_str = size_str[0:-4]
    return int(size_str)
