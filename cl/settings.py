"""Settings are derived by compiling any files ending in .py in the settings directory, in alphabetical order.

This results in the following concept:
 - default settings are in 10-public.py (this should contain most settings)
 - custom settings are in 05-private.py (an example of this file is here for you)
 - any overrides to public settings can go in 20-private.py (you'll need to create this)
"""

import os
import glob

conf_files = glob.glob(
    os.path.join(os.path.dirname(__file__), "settings", "*.py")
)
conf_files.sort()
for f in conf_files:
    execfile(os.path.abspath(f))

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
