alternative = [
    (1024 ** 5, 'PB'),
    (1024 ** 4, 'TB'),
    (1024 ** 3, 'GB'),
    (1024 ** 2, 'MB'),
    (1024 ** 1, 'KB'),
    (1024 ** 0, (' byte', ' bytes')),
]


def size(bytes, system=alternative):
    """Human-readable file size.

    """
    for factor, suffix in system:
        if bytes >= factor:
            break
    amount = float(bytes) / factor
    if isinstance(suffix, tuple):
        singular, multiple = suffix
        if amount == 1:
            suffix = singular
        else:
            suffix = multiple

    if suffix == 'PB':
        return '%.3f%s' % (amount, suffix)
    elif suffix == 'TB':
        return '%.2f%s' % (amount, suffix)
    elif suffix == 'GB':
        return '%.1f%s' % (amount, suffix)
    else:
        return '%d%s' % (amount, suffix)
