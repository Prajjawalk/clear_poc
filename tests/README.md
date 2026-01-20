# Testing Guide

This project uses three types of tests: backend unit/integration tests, frontend unit tests, and end-to-end tests.

## Quick Start

```bash
# Backend tests (886 tests)
cd django
uv run pytest

# Frontend tests (54 tests)
npm test

# E2E tests (21 tests) - with parallel execution
uv run pytest tests/e2e/ -n 4
```

---

## Running Backend Tests

**Location**: `django/<app>/tests/`
**Framework**: pytest
**Count**: 886 tests

```bash
cd django

# All backend tests
uv run pytest

# Specific app
uv run pytest alerts/tests/

# Specific test file
uv run pytest alerts/tests/test_models.py

# Specific test
uv run pytest alerts/tests/test_models.py::TestAlertModel::test_is_active_property

# Skip E2E tests
uv run pytest -m "not e2e"

# With coverage
uv run pytest --cov=. --cov-report=html
```

---

## Running Frontend Tests

**Location**: `django/frontend/js/__tests__/`
**Framework**: Vitest
**Count**: 54 tests

```bash
cd django

# Watch mode (default)
npm test

# Run once
npm run test:run

# With UI
npm run test:ui

# With coverage
npm run test:coverage
```

---

## Running E2E Tests

**Location**: `django/tests/e2e/`
**Framework**: pytest + Playwright
**Count**: 21 tests

```bash
cd django

# All E2E tests (sequential)
uv run pytest tests/e2e/ -v

# Parallel execution (16% faster)
uv run pytest tests/e2e/ -n 4     # 4 workers
uv run pytest tests/e2e/ -n auto  # Auto-detect CPUs

# Specific test
uv run pytest tests/e2e/test_authentication.py::test_login_page_loads

# With browser visible
uv run pytest tests/e2e/ --headed

# With debug logging
DEBUG_E2E=1 uv run pytest tests/e2e/ -v
```

---

## Test Markers

Filter tests using markers:

```bash
# Only unit tests
uv run pytest -m unit

# Skip E2E tests
uv run pytest -m "not e2e"

# Only fast tests
uv run pytest -m "not slow"
```

---

## Troubleshooting

### Backend tests not running

```bash
cd django
uv sync  # Reinstall dependencies
uv run pytest --version  # Verify pytest is installed
```

### E2E tests timing out

```bash
npm run build  # Build frontend assets first
uv run pytest tests/e2e/ -n 4  # Use parallel execution
DEBUG_E2E=1 uv run pytest tests/e2e/ -v  # Enable debug logging
```

### Frontend tests not running

```bash
npm install  # Reinstall dependencies
npm test  # Run tests
```

---

## Test Summary

| Test Type | Count | Framework | Command | Status |
|-----------|-------|-----------|---------|--------|
| Backend Unit/Integration | 886 | pytest | `uv run pytest` | ✅ Passing |
| Frontend Unit | 54 | Vitest | `npm test` | ✅ Passing |
| E2E | 21 | Playwright + pytest | `uv run pytest tests/e2e/ -n 4` | ✅ Passing |
| **Total** | **961** | - | - | **✅ 100%** |

---

## Project Structure

```
django/
├── alerts/tests/              # Backend unit/integration tests
├── data_pipeline/tests/       # Backend unit/integration tests
├── alert_framework/tests/     # Backend unit/integration tests
├── frontend/js/__tests__/     # Frontend unit tests (Vitest)
│   ├── alertMap.test.js
│   ├── dataMap.test.js
│   └── notifications.test.js
└── tests/
    └── e2e/                   # End-to-end tests (Playwright)
        ├── conftest.py        # Shared fixtures
        ├── test_alert_workflow.py
        ├── test_authentication.py
        └── test_data_pipeline_map.py
```
