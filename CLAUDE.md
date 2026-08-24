# CourtListener Development Guidelines

These guidelines help AI assistants work effectively on CourtListener.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD
NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as
described in [RFC 2119](https://www.rfc-editor.org/info/rfc2119/).

Rules and guidance on our wiki are written with flexibility for humans, but MUST be
strictly followed by AI agents. For example, if the wiki says that something "should" be
done, that's guidance to humans; AIs MUST do those things.

## Developer Guides

- **Getting Started**: https://wiki.free.law/c/courtlistener/dev-guide/getting-started.md

## Frontend

CourtListener has two frontend stacks (legacy Bootstrap/jQuery and new
Tailwind/Alpine/Cotton). Before writing any frontend code, MUST determine which stack
you're working in and MUST read `FRONTEND.md` for stack-specific rules. Do not mix stacks.

## Coding Rules

1. **URLs**: MUST use Django's `reverse()` function. NEVER hardcode URLs in backend code.
   ```python
   # Good
   from django.urls import reverse
   url = reverse("some_view_name", kwargs={"pk": 1})

   # Bad
   url = "/some/hardcoded/path/1/"
   ```

2. **Type Hints**: New code MUST include type hints and pass MyPy. MUST upgrade lint.yml
   with new files as you go.

3. **Unused Code**: MUST delete unused code created during a task.

4. **API Version**: MUST use API v4, never v3. v3 is deprecated.

5. **Management Commands**: MUST NOT add `cl_` to the names of management commands. It's
   an obsolete practice.

6. **Async Patterns**: Many views use async. Use `sync_to_async` and `async_to_sync` from
   `asgiref.sync` when needed.

7. **Imports**: MUST put imports at the top of the file; inline imports are permitted only
   to prevent circular dependency problems.

### Python Style Rules

1. SHOULD use modern python features like the walrus operator.

2. SHOULD use early exits to prevent deep nesting.
    ```python
    # Good
    if not some_condition:
       # Condition failed. Exit the function.
       return

    # Bad
    if some_condition:
       do_something()
    ```

3. MUST include docstrings for all methods, classes, functions, and types.
    1. Docstrings MUST explain the intended use of a function along with any caveats that
       callers should be aware of.
    2. Documentation SHOULD NOT explain implementation details except where doing so will
       help the caller.

4. MUST include comments explaining the reasoning behind complex or unintuitive code.
   SHOULD NOT include comments explaining basic code, language features, or other
   information that can be gleaned by skimming the code.

## Testing

### Test Base Classes

MUST read the testing guide before writing tests and follow it
strictly: https://wiki.free.law/c/courtlistener/dev-guide/automated-tests.md

MUST use `self.assertCondition` methods instead of bare `assert` statements since they
provide better failure diagnostics.

```python
def my_test(self):
    # Do this
    self.assertEqual(a, b)

    # Not this
    assert a == b
```

MUST use project-specific test classes from `cl.tests.cases`:

```python
from cl.tests.cases import SimpleTestCase, TestCase, APITestCase


class MySimpleTest(SimpleTestCase):
    """No database access needed"""
    pass


class MyDBTest(TestCase):
    """Needs database access"""
    pass


class MyAPITest(APITestCase):
    """For REST API tests"""
    pass
```

### Running Tests

```bash
# Run all tests for an app
docker exec cl-django python manage.py test --keepdb cl.appname.tests

# Run specific test class
docker exec cl-django python manage.py test --keepdb cl.appname.tests.TestClassName

# Run specific test method
docker exec cl-django python manage.py test --keepdb cl.appname.tests.TestClassName.test_method
```

### Testing Guidelines

- MAY omit `--keepdb` to ensure the test database is up to date
- SHOULD keep the database between test runs for efficiency
- SHOULD use `subTest()` to reduce test methods while testing multiple cases
- SHOULD avoid selenium tests (they're slow)
- MUST use `time_machine` for date-dependent tests to avoid flaky failures
- SHOULD use `FactoryBoy` to make mock data.
- MUST NOT use Django fixtures. If fixtures are found, MUST replace them with tests that
  use FactoryBoy and Fakes.

## Database Migrations

When creating code that modifies Django models, MUST strictly follow the Database
Migration guide: https://wiki.free.law/c/courtlistener/dev-guide/database-migrations.md

## Submitting Work

### Commits

- SHOULD break changes into logical commits (use `git add -p` for sub-file commits)
- MUST follow conventional commit format: `type(scope): message`
  ```
  feat(alerts): Add new notification system
  fix(search): Correct pagination bug
  docs(readme): Update installation steps
  refactor(api): Simplify serializer logic
  ```

### Pull Requests

1. MUST update branch before committing.
2. MUST run `pre-commit` and ensure it passes
3. MUST submit as **draft** PR
4. MUST use the template from `.github/PULL_REQUEST_TEMPLATE.md`

## Available Tools

### Docker Commands

```bash
# Run Django management commands
docker exec cl-django python manage.py [command]

# Access Django shell
docker exec -it cl-django python manage.py shell
```

### CLI Tools

- `rg` may be installed. Use it instead of `grep` if so.
- `gh` → GitHub CLI for PRs, issues, actions
- `pre-commit` → code quality checks (ruff, mypy, etc.). Its `check python ast`
  hook already validates Python syntax on every edited file — MUST rely on
  that instead of ad hoc `python -c "import ast; ast.parse(...)"` snippets.
- `uv` → Python dependency management (the only tool to use for deps)
