#!/usr/bin/env python
"""Django's command-line utility for CourtListener."""

import os
import sys


def main():
    """Run a Django management command from the command line."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cl.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
