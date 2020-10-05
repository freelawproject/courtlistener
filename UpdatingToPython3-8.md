# Updating to Python 3.8

Preliminary caveat: I haven't tested running the codebase after these changes, this is an introductory investigation. Currently the `reporters-db` dependency is the blocker to actually running the `manage.py`.

## Dependencies

Dependencies that needed updating:

- `pydot` version `1.1.0` is not compatible with Python 3. Update to version `20.9.0`.
- `pandas` version `0.18.1` is not compatible with Python 3(.8 ?). Update to version `1.1.2`. This also requires updating `python-dateutil` from `2.5.0` to `>=2.7.3` - updated to `2.8.1`.
- `pycopg2` version `2.7.7` needs updating. Update to `2.8.6`. Note that this requires `export CONFIGURE_OPTS="CPPFLAGS=-I$(brew --prefix openssl)/include" LDFLAGS="-L$(brew --prefix openssl)/lib"` on macOS.
- `wsgiref` is now built into Python 3, so isn't necessary to include as a dependency.
-` enum34` isn't necessary anymore.
- it's not possible to install `seal-rookery` from PyPI due to missing `sdist` distributions. As workaround, install directly from GitHub.
- `reporters-db` can't be installed because it relies on `python-dateutil==2.5.0`.
- `mock` is no longer needed as this is part of the standard library in `unittest.mock` as of py3.3.

## Code changes

Updating of the actual code:

- Run 2to3 and hand-modify the output to remove false positives and other automatic errors. It picked up a false positive around importing `from celery import Celery` when there was a local file called `celery.py`, and there were a bunch of false positives where 2to3 converts `for x, y in dict.values()` to `for x, y in list(dict.values())` which is unnecessary and inefficient. Other than that the results were pretty good. The main consideration going forwards is that somewhere there's a comparison between a `b"some bytes string"` and a `"some unicode string"` which can't be found at runtime but will never be equal. More details of 2to3 changes below.
- In `10-public.py`, the `maxBytes` setting needs to be changed to an int, not a string.
- `django.utils.encoding.smart_unicode` was renamed to `django.utils.encoding.smart_text` but it's actually just an alias to `django.utils.encoding.force_str`, so may as well just change it to that.
- Any instances of `import mock` or `from mock import ...` need to be trivially changed to `from unittest import mock` and `from unittest.mock import ...`.

### 2to3

This summaries the automatic conversions that 2to3 can apply:

- Remove `u"blah"` from strings to just be `"blah"` - in Python 3 these are equivalent.
- Change `isinstance(x, basestring)` to `isinstance(x, str)` as `basestring = (str, unicode)` doesn't exist in py3.
- Change `unicode(...)` to `str(...)`.
- Remove `from __future__ import unicode_literals`.
- Change `raw_input()` to `input()` and `input()` to `eval(input())` (note: no-where in this repo is the `eval()` bit required, so best to leave it off for obvious security reasons).
- Change `print "blah"` to `print("blah")` and `print "foo",` to `print("foo", end=" ")`.
- Remove `from __future__ import absolute_import`.
- Convert py2 method of importing local files `from local_file import myfunction` to py3 version: `from .local_file import myfunction`. You need to be careful that 2to3 doesn't get false positives where name of local file == local of repository, which happened once here.
- Replace `xrange()` with `range()`.
- Replace `execfile()` with `exec(compile(open("file.py").read(), "file.py", "exec"))`.
- Some functions like `dict.values()`, `dict.items()`, etc. return iterators instead of lists. Sometimes (but not always), you need to convert these to lists yourself to avoid strange bugs. For instance, `for x, y in d.items()` isn't necessary because you're immediately consuming the iterator, but if you do `d = {"a": 1}; x = d.items(); l1 = len(x); l2 = len(x)` then `l1 == 1` and `l2 == 0` because the first `len(x)` consumes the iterator meaning there's nothing left in it. Figuring out which one is immediately consumed and which isn't just needs to be done by hand.
- Change stdlib library names:
  - `httplib` => `http.client`
  - `HTMLParser` => `html.parser`
  - `StringIO => io.StringIO`
  - etc.
- Change `long` to `int`, as py2 `long`s are the same as py3 `int`s.
- Starting number with `0`, e.g. `07` is not valid in py3. Either use `0o7` for an octal or `7` for a decimal.
- Change dunder methods:  `__nonzero__` to `__bool__` and `__unicode__` to `__str__`.
- `reduce` needs to be imported from `functools`.

There's a bunch of other things too but they don't appear in the courtlistener codebase.

## Poetry

To install dependencies with Poetry, run:

```bash
poetry install

# If you don't want dev dependencies, you have to explicitly say so.
poetry install --no-dev

# If you want the extras, you need to say so.
poetry install -E flp
```

Then you can run the `manage.py` command using either:

```bash
poetry run manage.py
# OR
cl-manage
```

If you invoke `poetry` without being in a virtual environment, poetry will create one for you automatically and use that. If you're already activated, it'll use the venv that you've created. I prefer to create my own because it gives you more control of where the venv is:

```bash
python -m venv .venv
source ./.venv/bin/activate
poetry install

# cl-manage has now been installed into the virtualenv
which cl-manage
```
