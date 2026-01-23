# CourtListener Development Guidelines

These guidelines help AI assistants work effectively on CourtListener. Rules marked as MUST are mandatory for AI agents.

Rules and guidance on our wiki is written with flexibility for humans, but MUST be strictly followed by AI agents. For example, if it says that something "should" be done, that's guidance to humans. AIs MUST do those things.


## Developer Guides

- **Getting Started**: https://github.com/freelawproject/courtlistener/wiki/Getting-Started-Developing-CourtListener/


## Project Structure

```
cl/                     # Main Django project
├── assets/            # Static files, templates, React components
│   ├── templates/     # Django templates (base.html, etc.)
│   ├── react/         # React/TypeScript components
│   └── static-global/ # Global CSS/JS
├── lib/               # Shared utilities
├── tests/             # Test utilities and base classes
└── [app]/             # Individual Django apps (search, alerts, etc.)
```


## Coding Rules

1. **URLs**: MUST use Django's `reverse()` function. NEVER hardcode URLs in backend code.
   ```python
   # Good
   from django.urls import reverse
   url = reverse("some_view_name", kwargs={"pk": 1})

   # Bad
   url = "/some/hardcoded/path/1/"
   ```

2. **Type Hints**: New code MUST include type hints and pass MyPy. Upgrade lint.yml with new files as you go.

3. **Unused Code**: MUST delete unused code created during a task.

4. **API Version**: Always use API v4, never v3. v3 is deprecated.

5. **Management Commands**: Do not add `cl_` to the names of management commands. It's an obsolete practice.

6. **Async Patterns**: Many views use async. Use `sync_to_async` and `async_to_sync` from `asgiref.sync` when needed.

7. **Imports**: NEVER do inline imports except to prevent circular dependency problems. ALWAYS put imports at the top.

### Python Style Rules

1. Use modern python features like the walrus operator.

2. Prefer early exits to prevent deep nesting.
    ```python
    # Good
    if not some_condition:
       # Condition failed. Exit the function.
       return

    # Bad
    if some_condition:
       do_something()
    ```

## Testing

### Test Base Classes

Read the testing guide before writing tests and follow it strictly: https://github.com/freelawproject/courtlistener/wiki/Automated-tests-on-CourtListener

Use project-specific test classes from `cl.tests.cases`:

```python
from cl.tests.cases import SimpleTestCase, TestCase, APITestCase

class MySimpleTest(SimpleTestCase):
    """No database access needed"""
    pass

class MyDBTest(TestCase):
    """Needs database access"""
    fixtures = ["some_fixture.json"]

class MyAPITest(APITestCase):
    """For REST API tests"""
    pass
```

### Running Tests

```bash
# Run all tests for an app
docker exec cl-django python manage.py test cl.appname.tests

# Run specific test class
docker exec cl-django python manage.py test cl.appname.tests.TestClassName

# Run specific test method
docker exec cl-django python manage.py test cl.appname.tests.TestClassName.test_method
```

### Testing Guidelines

- Keep the database between test runs for efficiency
- Use `subTest()` to reduce test methods while testing multiple cases
- Avoid selenium tests unless necessary (they're slow)
- Use `time_machine` for date-dependent tests to avoid flaky failures
- Use `FactoryBoy` to make mock data.
- NEVER use Django fixtures. If fixtures are found, replace them with tests that use FactoryBoy and Fakes.


## Database Migrations

When creating code that modify Django models, strictly follow the Database Migration guide: https://github.com/freelawproject/courtlistener/wiki/Database-migrations


## Submitting Work

### Commits

- Break changes into logical commits (use `git add -p` for sub-file commits)
- Follow conventional commit format: `type(scope): message`
  ```
  feat(alerts): Add new notification system
  fix(search): Correct pagination bug
  docs(readme): Update installation steps
  refactor(api): Simplify serializer logic
  ```

### Pull Requests

1. ALWAYS update branch before committing.
2. ALWAYS run `pre-commit` and ensure it passes
3. ALWAYS submit as **draft** PR
4. ALWAYS use the template from `.github/PULL_REQUEST_TEMPLATE.md`


## Available Tools

### Docker Commands

```bash
# Run Django management commands
docker exec cl-django python manage.py [command]

# Run tests
docker exec cl-django python manage.py test [test_path]

# Access Django shell
docker exec -it cl-django python manage.py shell
```

### CLI Tools

- `rg` may be installed. Use it instead of `grep` if so.
- `gh` → GitHub CLI for PRs, issues, actions
- `pre-commit` → code quality checks (ruff, mypy, etc.)
- `uv` → Python dependency management (the only tool to use for deps)
