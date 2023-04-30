#!/usr/bin/env python
from gevent import monkey

monkey.patch_all()
from psycogreen.gevent import patch_psycopg

patch_psycopg()
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cl.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
