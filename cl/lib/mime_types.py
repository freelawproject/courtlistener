# coding=utf8
"""
Mime type lookup helpers
"""

MIME_TYPES = {
    'mp3': 'audio/mpeg',
    'pdf': 'application/pdf',
    'txt': 'text/plain',
    'doc': 'application/msword',
    'dot': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'dotx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.template',
    'docm': 'application/vnd.ms-word.document.macroEnabled.12',
    'dotm': 'application/vnd.ms-word.template.macroEnabled.12',
    'xls': 'application/vnd.ms-excel',
    'xlt': 'application/vnd.ms-excel',
    'xla': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'xltx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.template',
    'xlsm': 'application/vnd.ms-excel.sheet.macroEnabled.12',
    'xltm': 'application/vnd.ms-excel.template.macroEnabled.12',
    'xlam': 'application/vnd.ms-excel.addin.macroEnabled.12',
    'xlsb': 'application/vnd.ms-excel.sheet.binary.macroEnabled.12',
    'ppt': 'application/vnd.ms-powerpoint',
    'pot': 'application/vnd.ms-powerpoint',
    'pps': 'application/vnd.ms-powerpoint',
    'ppa': 'application/vnd.ms-powerpoint',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'potx': 'application/vnd.openxmlformats-officedocument.presentationml.template',
    'ppsx': 'application/vnd.openxmlformats-officedocument.presentationml.slideshow',
    'ppam': 'application/vnd.ms-powerpoint.addin.macroEnabled.12',
    'pptm': 'application/vnd.ms-powerpoint.presentation.macroEnabled.12',
    'potm': 'application/vnd.ms-powerpoint.presentation.macroEnabled.12',
    'ppsm': 'application/vnd.ms-powerpoint.slideshow.macroEnabled.12'
}

DEFAULT_MIME_TYPE = 'application/octet-stream'


def lookup_mime_type(file_path):
    """
    Do a simple dictionary lookup of the mime-type for the given file.
    :param file_path Full or relative path to the given file.
    """
    try:
        extension = file_path.split('.')[-1]
        return MIME_TYPES[extension]
    except KeyError:
        return DEFAULT_MIME_TYPE
