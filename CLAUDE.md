# CLAUDE.md - CourtListener AI Assistant Guide

This document provides guidance for AI assistants working with the CourtListener codebase.

## Project Overview

CourtListener is a free legal research platform operated by Free Law Project. It provides access to court opinions, PACER/RECAP documents, oral arguments, judicial financial disclosures, and judge information. The platform includes a REST API, search functionality powered by Elasticsearch, and various data processing pipelines.

**Tech Stack:**
- Python 3.13, Django 5.1
- PostgreSQL 15 with pghistory for audit trails
- Elasticsearch 9.0 for search
- Redis for caching and sessions
- Celery for async task processing
- Docker Compose for local development

## Repository Structure

```
courtlistener/
├── cl/                     # Main Django application (99% of code)
│   ├── alerts/            # Search and docket alerts
│   ├── api/               # REST API (DRF) - v3 and v4 endpoints
│   ├── audio/             # Oral argument audio files
│   ├── citations/         # Citation parsing and linking
│   ├── corpus_importer/   # Data import from various sources
│   ├── custom_filters/    # Template filters
│   ├── disclosures/       # Judicial financial disclosures
│   ├── donate/            # Donation handling
│   ├── favorites/         # User tags, prayers, bookmarks
│   ├── lasc/              # LA Superior Court integration
│   ├── lib/               # Shared utilities and helpers
│   ├── opinion_page/      # Opinion display views
│   ├── people_db/         # Judges, attorneys, parties
│   ├── recap/             # PACER/RECAP document processing
│   ├── recap_rss/         # PACER RSS feed scraping
│   ├── scrapers/          # Court website scrapers
│   ├── search/            # Search models, views, Elasticsearch
│   ├── settings/          # Django settings (modular)
│   ├── simple_pages/      # Static/simple pages
│   ├── sitemaps_infinite/ # Sitemap generation
│   ├── stats/             # Usage statistics
│   ├── tests/             # Shared test utilities
│   ├── users/             # User accounts and profiles
│   └── visualizations/    # Citation network visualizations
├── docker/                # Docker configuration
│   ├── courtlistener/     # docker-compose files
│   ├── django/            # Django Dockerfile and entrypoint
│   ├── elastic/           # Elasticsearch certs
│   └── postgresql/        # PostgreSQL config
├── scripts/               # Deployment and maintenance scripts
├── manage.py              # Django management script
├── pyproject.toml         # Python dependencies (uv)
└── uv.lock                # Locked dependencies
```

## Development Setup

### Docker Environment

```bash
# Create network
docker network create -d bridge --attachable cl_net_overlay

# Copy and configure environment
cp .env.example .env.dev
# Edit .env.dev: set SECRET_KEY, ALLOWED_HOSTS=*

# Start services
cd docker/courtlistener
docker compose up -d

# Access the app at http://localhost:8000
```

### Key Services
- `cl-django`: Web server (port 8000)
- `cl-celery`: Async task worker
- `cl-postgres`: PostgreSQL database (port 5432)
- `cl-redis`: Cache and session store
- `cl-es`: Elasticsearch (port 9200)
- `cl-selenium`: Browser testing

### Running Commands

```bash
# Run Django management commands
docker exec cl-django ./manage.py <command>

# Run tests
docker exec cl-django ./manage.py test cl --verbosity=2 --parallel

# Run specific test
docker exec cl-django ./manage.py test cl.search.tests.tests.SomeTestClass

# Migrations
docker exec cl-django ./manage.py makemigrations
docker exec cl-django ./manage.py migrate
```

## Code Style and Linting

### Pre-commit Hooks
The project uses pre-commit with:
- `ruff` for linting and formatting (line length: 79)
- Standard pre-commit checks (trailing whitespace, YAML, JSON, etc.)

```bash
# Run pre-commit manually
pre-commit run --all-files
```

### Ruff Configuration (pyproject.toml)
- Line length: 79 characters
- Enabled: pycodestyle (E), Pyflakes (F), isort (I), pyupgrade (UP)
- Migrations are excluded from linting

### Type Checking
```bash
# mypy is run in CI for specific packages
uv run mypy --follow-imports=skip -p cl.alerts -p cl.search ...
```

The project uses Django stubs and DRF stubs. See `.github/workflows/lint.yml` for the full list of type-checked modules.

## Testing

### Test Framework
- Django's test framework with custom base classes in `cl/tests/cases.py`
- Factory Boy for test data generation (`**/factories.py`)
- Selenium for browser tests (tagged with `selenium`)

### Test Base Classes
```python
from cl.tests.cases import TestCase, TransactionTestCase, APITestCase, ESIndexTestCase

# Standard Django tests
class MyTest(TestCase):
    pass

# Tests requiring Elasticsearch
class MyESTest(ESIndexTestCase):
    pass
```

### Running Tests
```bash
# All tests (excluding selenium)
docker exec cl-django ./manage.py test cl --exclude-tag selenium --parallel

# Selenium tests only
docker exec cl-django ./manage.py test cl --tag selenium

# Check for missing migrations
docker exec cl-django ./manage.py makemigrations --check --dry-run
```

### Factory Pattern
Each app has a `factories.py` file using Factory Boy:
```python
from cl.search.factories import DocketFactory, OpinionClusterFactory

# Create test data
docket = DocketFactory()
cluster = OpinionClusterFactory(docket=docket)
```

## Django Apps and Key Models

### Core Search Models (`cl/search/models.py`)
- `Court`: Court/jurisdiction metadata
- `Docket`: Case container (from PACER or scrapers)
- `DocketEntry`: Individual entries in a docket
- `RECAPDocument`: PDF documents from PACER
- `OpinionCluster`: Group of related opinions
- `Opinion`: Individual opinion text
- `Citation`: Citation references

### People Models (`cl/people_db/models.py`)
- `Person`: Judges and other individuals
- `Position`: Judicial appointments
- `Attorney`, `Party`: Case participants

### Alert Models (`cl/alerts/models.py`)
- `Alert`: Search alerts
- `DocketAlert`: Docket-specific alerts

### User Models (`cl/users/models.py`)
- Extended Django User with `UserProfile`

## API Structure

### Versioning
- **v3**: Legacy API (still supported)
- **v4**: Current API with improved search

### Endpoints
All endpoints at `/api/rest/v{3,4}/`:
- `/dockets/`, `/docket-entries/`, `/recap-documents/`
- `/clusters/`, `/opinions/`, `/opinions-cited/`
- `/courts/`, `/audio/`, `/search/`
- `/people/`, `/positions/`, `/attorneys/`, `/parties/`
- `/alerts/`, `/docket-alerts/`
- `/financial-disclosures/`, `/investments/`, etc.

### Authentication
- Token authentication via DRF
- Tokens in `Authorization: Token <token>` header

### Example API Usage
```python
# In tests
from rest_framework.test import APIClient
client = APIClient()
client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
response = client.get('/api/rest/v4/search/', {'q': 'test'})
```

## Celery Tasks

### Configuration
- Celery app in `cl/celery_init.py`
- Tasks autodiscovered from `tasks.py` in each app
- Redis as broker

### Common Task Patterns
```python
from celery import shared_task
from cl.lib.celery_utils import throttle_task

@shared_task
@throttle_task("10/m")  # Rate limiting
def my_task(arg):
    pass
```

### Key Task Files
- `cl/search/tasks.py`: Indexing, ES updates
- `cl/alerts/tasks.py`: Alert sending
- `cl/recap/tasks.py`: PACER document processing
- `cl/corpus_importer/tasks.py`: Data import

## Management Commands

Commands follow the pattern `cl_<action>` and are in `<app>/management/commands/`:

### Common Commands
```bash
# Scraping
./manage.py cl_scrape_opinions
./manage.py cl_scrape_oral_arguments
./manage.py scrape_rss

# Indexing
./manage.py cl_index_parent_and_child_docs
./manage.py sweep_indexer

# Alerts
./manage.py cl_send_alerts
./manage.py cl_send_scheduled_alerts

# Data import
./manage.py harvard_opinions
./manage.py import_idb

# Maintenance
./manage.py clear_cache
./manage.py make_dev_data
```

## Elasticsearch

### Index Documents (`cl/search/documents.py`)
- `DocketDocument`: Dockets and their entries
- `OpinionClusterDocument`: Opinion clusters
- `PersonDocument`: Judge information
- `AudioDocument`: Oral arguments

### Index Management
```bash
# Rebuild an index
docker exec cl-django ./manage.py search_index --rebuild -f --models search.Docket

# Create index
docker exec cl-django ./manage.py search_index --create -f --models search.OpinionCluster
```

## Settings Structure

Settings are modular in `cl/settings/`:
```
settings/
├── __init__.py      # Imports all settings
├── django.py        # Core Django settings
├── misc.py          # Miscellaneous settings
├── project/         # Project-specific settings
│   ├── email.py
│   ├── logging.py
│   ├── search.py
│   ├── security.py
│   └── testing.py
└── third_party/     # Third-party service configs
    └── redis.py
```

Environment variables are loaded via `django-environ` with `.env` file support.

## Pull Request Guidelines

### PR Template Checklist
1. **Fixes**: Link to issue being fixed
2. **Summary**: Description of changes
3. **Deployment labels**:
   - `skip-deploy`: Skip all deployment
   - `skip-web-deploy`: Skip web tier
   - `skip-celery-deploy`: Skip Celery workers
   - `skip-cronjob-deploy`: Skip cron jobs
   - `skip-daemon-deploy`: Skip daemons

### CI Checks
- Pre-commit hooks (ruff, etc.)
- mypy type checking
- Full test suite (parallel)
- Selenium tests
- Migration check
- CodeQL security analysis
- Semgrep static analysis

## Common Patterns

### Creating a New Feature
1. Add models to appropriate app's `models.py`
2. Create and run migrations
3. Add factories in `factories.py`
4. Write tests in `tests.py` or `tests/`
5. Add API serializers/views if needed
6. Update admin if needed

### Adding an API Endpoint
1. Create serializer in `api_serializers.py`
2. Create viewset in `api_views.py`
3. Register in `cl/api/urls.py` router
4. Add tests
5. Update API documentation

### Database Migrations
```bash
# Create migration
docker exec cl-django ./manage.py makemigrations <app_name>

# Apply migrations
docker exec cl-django ./manage.py migrate

# Check for missing migrations (CI does this)
docker exec cl-django ./manage.py makemigrations --check --dry-run
```

## Important Conventions

1. **Imports**: Use absolute imports from `cl.*`
2. **Models**: Use `AbstractDateTimeModel` for timestamps
3. **Tests**: Use factories, not fixtures
4. **API**: Support both v3 and v4 where applicable
5. **Async**: Use `sync_to_async`/`async_to_sync` from asgiref
6. **Logging**: Use module-level logger: `logger = logging.getLogger(__name__)`

## External Dependencies

### Key Libraries
- `juriscraper`: Court scraping framework
- `eyecite`: Citation extraction
- `courts-db`: Court metadata
- `reporters-db`: Reporter metadata
- `judge-pics`: Judicial portraits

### External Services
- PACER: Federal court documents
- Internet Archive: Document archival
- AWS S3: File storage (production)
- Sentry: Error tracking
- Plausible: Analytics

## Debugging Tips

1. **Docker logs**: `docker compose logs -f cl-django`
2. **Django shell**: `docker exec -it cl-django ./manage.py shell`
3. **Database**: `docker exec -it cl-django ./manage.py dbshell`
4. **Elasticsearch**: Check `http://localhost:9200` (auth: elastic/password)
5. **Celery**: Monitor with `celery -A cl events`

## Security Notes

- Never commit secrets (use `.env` files)
- Rate limiting is enabled (`django-ratelimit`)
- CSP headers configured (`django-csp`)
- CORS configured (`django-cors-headers`)
- pghistory tracks model changes for audit

## Resources

- [Developer Guide](https://github.com/freelawproject/courtlistener/wiki/Getting-Started-Developing-CourtListener)
- [API Documentation](https://www.courtlistener.com/help/api/)
- [Free Law Project](https://free.law/)
