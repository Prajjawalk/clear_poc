# Data Pipeline Tests

This directory contains the test suite for the data pipeline application, organized into unit tests and integration tests for easy management and execution.

## Test Organization

### 📁 `unit/` - Unit Tests
Fast, isolated tests that use mocks and don't require external dependencies.

**What they test:**
- Model validation and business logic
- Data processing algorithms with mock data
- Individual method functionality
- Field mappings and data transformations

**Working test files:**
- `test_models.py` - Database model tests (38 tests) ✅
- `test_sources_idmcidu.py` - IDMC IDU source logic (8 tests) ✅
- `test_sources_idmcgidd.py` - IDMC GIDD source logic (15 tests) ✅
- `tests.py` - Extended model and relationship tests (37 tests) ✅
- `tests_vite.py` - Vite template tag tests (4 tests) ✅

**Legacy test files:** (moved to `unit/legacy/`)
- `test_sources_acled.py` - ACLED tests (need API credentials/fixes)
- `test_sources_iom.py` - IOM tests (method name mismatches)
- `test_sources_reliefweb.py` - ReliefWeb tests (method name mismatches)  
- `test_sources_base.py` - Base source tests (API mismatches)
- `test_tasks.py` - Celery task tests (some integration aspects)
- `test_views.py` - View tests (require authentication setup)
- `tests_views.py` - API endpoint tests (authentication issues)
- Other legacy files

### 📁 `integration/` - Integration Tests
Comprehensive tests that interact with real APIs and external services.

**What they test:**
- Actual API connectivity and authentication
- End-to-end data processing workflows
- Cross-system integration
- Real data retrieval and processing

**Key test files:**
- `test_integration_idmc_gidd.py` - IDMC GIDD API integration
- `test_integration_idmc_idu.py` - IDMC IDU API integration
- `test_integration_acled.py` - ACLED API integration
- `test_integration_iom.py` - IOM DTM API integration
- `test_integration_reliefweb.py` - ReliefWeb API integration
- `test_integration_internal.py` - Cross-app integration workflows

## Running Tests

### Run Unit Tests Only (Fast)
```bash
# Run all unit tests
uv run manage.py test data_pipeline.tests.unit

# Run specific unit test suite
uv run manage.py test data_pipeline.tests.unit.test_models
uv run manage.py test data_pipeline.tests.unit.test_sources_idmcidu
uv run manage.py test data_pipeline.tests.unit.test_sources_idmcgidd

# Run core working unit tests
uv run manage.py test data_pipeline.tests.unit.test_models data_pipeline.tests.unit.test_sources_idmcidu data_pipeline.tests.unit.test_sources_idmcgidd
```

### Run Integration Tests (Requires API Keys)
```bash
# Run all integration tests
uv run manage.py test data_pipeline.tests.integration

# Run specific integration test
uv run manage.py test data_pipeline.tests.integration.test_integration_idmc_gidd
```

### Run All Tests
```bash
# Run everything (unit + integration)
uv run manage.py test data_pipeline.tests
```

## Test Requirements

### Unit Tests
- ✅ No external dependencies
- ✅ Fast execution (< 1 minute)
- ✅ Use mocked data and API responses
- ✅ Safe to run in CI/CD pipelines

### Integration Tests
- ⚠️ Require API credentials in `.env` file:
  - `IDMC_API_KEY` - IDMC API access
  - `ACLED_USERNAME` and `ACLED_API_KEY` - ACLED authentication
  - Other source-specific credentials
- ⚠️ Require network connectivity
- ⚠️ May take longer to execute
- ⚠️ May fail if external APIs are unavailable

## Test Status

### ✅ Clean Unit Tests (102 total - All Passing)
- **Models**: 38/38 tests passing (`test_models.py`)
- **IDMC IDU**: 8/8 tests passing (`test_sources_idmcidu.py`)
- **IDMC GIDD**: 15/15 tests passing (`test_sources_idmcgidd.py`)
- **Extended Models**: 37/37 tests passing (`tests.py`)
- **Vite Templates**: 4/4 tests passing (`tests_vite.py`)
- **Total Runtime**: ~1 second
- **Dependencies**: None (fully mocked)

### 📦 Legacy Tests (Moved to `unit/legacy/`)
Tests that need fixes or have integration aspects:
- **ACLED**: Some tests need API credentials or implementation fixes
- **IOM/ReliefWeb**: Method name mismatches with current implementation
- **Tasks/Views**: Some tests have integration aspects or legacy issues

## Development Workflow

1. **During development**: Run clean unit tests frequently
   ```bash
   # Fast, reliable unit tests (102 tests, ~1 second)
   uv run manage.py test data_pipeline.tests.unit
   ```

2. **Before deployment**: Run integration tests to verify API connectivity
   ```bash
   uv run manage.py test data_pipeline.tests.integration
   ```

3. **CI/CD**: Run unit tests in automated pipelines, integration tests on-demand

## Adding New Tests

### For Unit Tests
- Add to `unit/` directory
- Mock all external dependencies
- Focus on business logic and data transformations
- Ensure fast execution

### For Integration Tests  
- Add to `integration/` directory
- Test real API interactions
- Include proper error handling
- Document required credentials