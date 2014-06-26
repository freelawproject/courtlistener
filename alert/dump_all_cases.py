import os
import sys

execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

from alert.lib.dump_lib import dump_it_all


def main():
    """
    A simple function that dumps all cases to a single dump file.
    """
    dump_it_all()

    exit(0)

if __name__ == '__main__':
    main()
