__author__ = '$USER'

import argparse
import os


def case_generator(dir_root):
    """Yield cases, one by one to the importer by recursing and iterating the import directory"""



def import_law_box_case(case):
    curent_case = case_generator()


def readable_dir(prospective_dir):
    if not os.path.isdir(prospective_dir):
        raise argparse.ArgumentTypeError("readable_dir:{0} is not a valid path".format(prospective_dir))
    if os.access(prospective_dir, os.R_OK):
        return prospective_dir
    else:
        raise argparse.ArgumentTypeError("readable_dir:{0} is not a readable dir".format(prospective_dir))


def main():
    parser = argparse.ArgumentParser(description='Import the corpus provided by lawbox')
    #parser.add_argument('-m', '--my-foo', default=True, required=False, action='store_true',
    #                    help='Do we foo it?')
    parser.add_argument('-r', '--root', type=readable_dir, default='/sata/dump/',
                        help='The directory where the lawbox dump can be found.')
    args = parser.parse_args()

    for case in case_generator(args.root):
        import_law_box_case()


    if __name__ == '__main__':
        main()
