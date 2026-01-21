# NRC EWAS Sudan

Early Warning and Alert System (EWAS) for Sudan - A Django web application for monitoring, analyzing, and managing humanitarian alerts and data pipelines.

## Overview

NRC EWAS Sudan is a geospatial web application designed to support humanitarian operations in Sudan through:

- **Alert Management**: Create, track, and visualize humanitarian alerts on interactive maps
- **Data Pipeline**: Collect, process, and analyze data from multiple sources
- **Notification System**: Real-time notifications for critical events
- **User Management**: Role-based access control and user subscriptions
- **Task Monitoring**: Track background jobs and data processing workflows
- **LLM Integration**: AI-powered analysis and insights

## Tech Stack

### Backend

- **Django 5.2+** - Web framework with GeoDjango for geospatial features
- **PostgreSQL + PostGIS** - Database with geospatial extensions
- **Celery** - Distributed task queue for background jobs
- **Redis** - Message broker and cache backend
- **TiTiler** - Dynamic tile server for raster data

### Frontend

- **Vite** - Fast build tool and dev server
- **Bootstrap 5** - UI framework
- **Leaflet** - Interactive maps with clustering support
- **Vanilla JavaScript** - No framework, pure ES6+

### Data Processing

- **Pandas & GeoPandas** - Data analysis and geospatial operations
- **Rasterio** - Raster data processing
- **OpenAI API** - LLM integration for analysis

## Prerequisites

- **Python 3.12+**
- **uv** - Python package manager
- **Node.js 18+** - For frontend build
- **PostgreSQL** with PostGIS extension
- **Redis** - For Celery task queue
- **GDAL** - Geospatial libraries

### System Dependencies

**Ubuntu/Debian**:

```bash
sudo apt update
sudo apt install -y python3.12 postgresql postgresql-contrib postgis redis-server
sudo apt install -y gdal-bin libgdal-dev libgeos-dev libproj-dev
```

**macOS**:

```bash
brew install python@3.12 postgresql postgis redis gdal
brew services start postgresql
brew services start redis
```

## Installation

### 1. Clone and Navigate

```bash
cd .
```

### 2. Environment Configuration

Copy the example environment files:

```bash
cp .env.example .env
cp .envrc_sample .envrc
```

Edit `.env` and `.envrc` with your configuration:

- Database credentials
- Django secret key
- API keys (OpenAI, DTM, Slack)
- Redis connection settings

### 3. Install Dependencies

```bash
# Install Python dependencies
uv sync

# Install Node.js dependencies
npm install

# Allow direnv (if using)
direnv allow
```

### 4. Database Setup

```bash
# Create PostgreSQL database with PostGIS
createdb nrc_ewas
psql -d nrc_ewas -c "CREATE EXTENSION postgis;"

# Run migrations
uv run manage.py migrate

# Load initial data (optional)
uv run manage.py loaddata app/fixtures/initial_data.json
```

### 5. Build Frontend Assets

```bash
npm run build
```

### 6. Create Superuser

```bash
uv run manage.py createsuperuser
```

## Development

### Running the Application

**Full stack with Celery** (recommended):

```bash
npm run dev
```

This starts:

- Django development server (http://localhost:8000)
- Vite dev server with HMR (http://localhost:5173)
- Celery worker for background tasks
- TiTiler server for raster tiles

**Without Celery** (lightweight):

```bash
npm run dev:light
```

**Individual services**:

```bash
# Django only
npm run dev:django

# Vite only (frontend hot reload)
npm run dev:vite

# Celery worker only
npm run dev:celery

# TiTiler server only
npm run dev:titiler
```

### Application Structure

```
django/
├── alerts/                    # Alert management system
├── alert_framework/           # Alert framework and rules
├── data_pipeline/             # Data collection and processing
├── dashboard/                 # Main dashboard views
├── location/                  # Location and boundary management
├── notifications/             # Notification system
├── users/                     # User management and authentication
├── task_monitoring/           # Celery task monitoring
├── llm_service/               # LLM integration service
├── translation/               # i18n string management
├── app/                       # Main Django project
│   ├── settings/              # Split settings (core, dev, test)
│   ├── templates/             # Base templates
│   └── views.py               # Main views
├── frontend/                  # Frontend assets
│   ├── js/                    # JavaScript modules
│   ├── css/                   # Stylesheets
│   └── static/                # Static files
└── tests/                     # Test suite
    └── e2e/                   # End-to-end tests
```

## Testing

Run the complete test suite (961 tests):

```bash
# Backend unit/integration tests (886 tests)
uv run pytest

# Frontend unit tests (54 tests)
npm test

# E2E tests with parallel execution (21 tests)
uv run pytest tests/e2e/ -n 4
```

See [tests/README.md](tests/README.md) for detailed testing documentation.

## Production Deployment

### Build for Production

```bash
# Build optimized frontend assets
npm run build:prod

# Collect static files
uv run manage.py collectstatic --noinput
```

### Environment Configuration

Set environment variables:

```bash
export DJANGO_ENV=PROD
export DEBUG=False
export ALLOWED_HOSTS='["your-domain.com"]'
```

### Run with uWSGI

```bash
uv run uwsgi --ini uwsgi.ini
```

### Celery in Production

```bash
# Worker
celery -A app worker --loglevel=info

# Beat scheduler
celery -A app beat --loglevel=info
```

## Configuration

### Django Settings

Settings are split into multiple files in `app/settings/`:

- `core.py` - Base configuration
- `dev.py` - Development settings
- `test.py` - Test configuration
- `logging.py` - Logging setup

### Celery Queues

The application uses multiple Celery queues:

- `celery` - Default queue
- `data_retrieval` - Data fetching tasks
- `data_processing` - Data processing tasks
- `data_aggregation` - Aggregation tasks
- `pipeline` - Pipeline orchestration

## VSCode Setup

Recommended VSCode extensions:

- Python (`ms-python.python`)
- Ruff (`charliermarsh.ruff`)
- Vitest (`vitest.explorer`)
- Django (`batisteo.vscode-django`)

See the included `.vscode/settings.json` and `.vscode/extensions.json` in the repository.

## Troubleshooting

### Redis Connection Error

```bash
# Check Redis is running
redis-cli ping  # Should return PONG

# Start Redis
sudo service redis start  # Linux
brew services start redis  # macOS
```

### Database Connection Error

```bash
# Verify PostgreSQL is running
pg_isready

# Check PostGIS extension
psql -d nrc_ewas -c "SELECT PostGIS_version();"
```

### Frontend Build Issues

```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
npm run build
```

### Celery Not Processing Tasks

```bash
# Check Celery worker is running
celery -A app inspect active

# Verify Redis connection
celery -A app inspect ping
```

## License

Internal project for Norwegian Refugee Council (NRC).

## Contact

For questions or support, contact: Philibert de Mercey (pdemercey@masae-analytics.com)
