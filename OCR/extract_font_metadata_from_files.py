from optparse import OptionParser
import operator
import os
import subprocess


DEVNULL = open('/dev/null', 'w')
def inspect(dir_name):
    """Get font information from PDFs.

    Recursively iterate over all the pdfs in a directory. For each found,
    extract the font information and throw it in a dictionary with a count. Sort
    the dict; print it out."""

    pdfs = []
    for r, d, f in os.walk(dir_name):
        for files in f:
            if files.endswith(".pdf"):
                 pdfs.append(os.path.join(r, files))
    fonts = {}
    for pdf in pdfs:
        # Extract the font information
        process = subprocess.Popen(["pdffonts", pdf], shell=False,
                                   stdout=subprocess.PIPE, stderr=DEVNULL)
        content, err = process.communicate()
        for line in content.split('\n')[2:-1]:
            font_with_plus = line.split(' ')[0]
            try:
                font = font_with_plus.split('+')[1]
            except IndexError:
                font = font_with_plus.split('+')[0]
            try:
                count = fonts[font]
                fonts[font] = count + 1
            except KeyError:
                fonts[font] = 1

    sorted_fonts = sorted(fonts.items(), key=operator.itemgetter(1), reverse=True)
    for font_count in sorted_fonts:
        print '%s, %s' % font_count




def main():
    usage = "usage: %prog -d <path-to-pdfs>"
    parser = OptionParser(usage)
    parser.add_option('-d', '--directory', dest='dir_name',
                      metavar='DIRECTORY_NAME', help=('All PDFs under this ',
                              'location will be inspected. Use an absolute path.'))
    (options, args) = parser.parse_args()

    return inspect(options.dir_name)
    exit(0)

if __name__ == '__main__':
    main()
