# End-to-End (E2E) Testing with Playwright

## Overview

E2E tests use Playwright to automate browser interactions and test complete user workflows in the NRC EWAS Sudan application.

**Status:** ✅ Setup Complete - 21 E2E tests (100% passing)

---

## What's Included

### Test Files Created

1. **[test_alert_workflow.py](test_alert_workflow.py)** - 7 tests
   - Alert map displays alerts
   - Alert map filtering (shock type, severity, date)
   - Alert popup displays details
   - Reset filters functionality
   - Alert list view
   - Map legend displays
   - Fullscreen functionality

2. **[test_data_pipeline_map.py](test_data_pipeline_map.py)** - 8 tests
   - Data pipeline map loads
   - Source filtering
   - Variable filtering
   - Apply filters
   - Reset filters
   - Zoom to data
   - Toggle clustering
   - Base layer control

3. **[test_authentication.py](test_authentication.py)** - 6 tests
   - Login page loads
   - Login with valid credentials
   - Login with invalid credentials
   - Homepage loads
   - Navigation menu exists
   - Responsive mobile view

### Supporting Files

- **[conftest.py](conftest.py)** - Pytest fixtures and helpers
  - Browser configuration
  - Test user fixtures (`test_user`, `admin_user`)
  - Test data fixtures (`test_location`, `test_shock_types`, `test_alerts`)
  - Helper functions (`wait_for_map_ready`, `wait_for_markers`, etc.)

---

## Installation

Already completed:

```bash
# Install Python packages
uv add --dev playwright pytest-playwright pytest-django

# Install browser binaries
uv run playwright install chromium

# Install system dependencies (if needed)
uv run playwright install-deps chromium
```

---

## Configuration

### pytest.ini
```ini
[pytest]
DJANGO_SETTINGS_MODULE = app.settings.core
testpaths = tests

markers =
    e2e: End-to-end tests using Playwright
    slow: Slow tests
```

### Environment Variables
Set in `conftest.py`:
```python
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
```

---

## Running E2E Tests

### Prerequisites

1. **Frontend Build** - Vite assets must be built:
   ```bash
   npm run build
   ```

2. **Django Server** - Tests use `live_server` fixture (starts automatically)

### Basic Commands

```bash
# Run all E2E tests
uv run pytest tests/e2e/ -m e2e

# Run specific test file
uv run pytest tests/e2e/test_alert_workflow.py

# Run specific test
uv run pytest tests/e2e/test_authentication.py::test_login_with_valid_credentials

# Run with visible browser (for debugging)
uv run pytest tests/e2e/ -m e2e --headed

# Run in specific browser
uv run pytest tests/e2e/ --browser chromium
uv run pytest tests/e2e/ --browser firefox

# Verbose output
uv run pytest tests/e2e/ -v -s

# Keep database between runs
uv run pytest tests/e2e/ --reuse-db
```

### Advanced Options

```bash
# Slow motion (for watching tests)
uv run pytest tests/e2e/ --slowmo 1000

# Take screenshots on failure
uv run pytest tests/e2e/ --screenshot on-failure

# Record video
uv run pytest tests/e2e/ --video on

# Run in parallel (with pytest-xdist) - 16% faster
uv run pytest tests/e2e/ -n 4
uv run pytest tests/e2e/ -n auto
```

---

## Test Structure

### Typical E2E Test Pattern

```python
@pytest.mark.e2e
@pytest.mark.django_db
def test_user_workflow(page: Page, live_server, test_alerts):
    """Test description."""
    # 1. Navigate to page
    page.goto(f"{live_server.url}/alerts/map/")

    # 2. Wait for elements
    page.wait_for_selector("#alert-map")

    # 3. Interact
    page.click(".some-button")

    # 4. Assert expectations
    expect(page.locator(".result")).to_be_visible()
```

### Available Fixtures

- `page` - Playwright page object (browser tab)
- `live_server` - Django test server URL
- `test_user` - Regular test user
- `admin_user` - Admin test user
- `test_location` - Test location (Khartoum)
- `test_shock_types` - Conflict and Flood shock types
- `test_alerts` - 2 test alerts
- `authenticated_page` - Pre-logged in browser page
- `admin_page` - Pre-logged in admin page

---

## Common Patterns

### Waiting for Elements

```python
# Wait for selector
page.wait_for_selector("#map", timeout=10000)

# Wait for map to be ready
page.wait_for_function(
    "document.querySelector('#map')._leaflet_id !== undefined",
    timeout=5000
)

# Wait for multiple markers
page.wait_for_function(
    "document.querySelectorAll('.leaflet-marker-icon').length >= 2"
)
```

### Assertions

```python
from playwright.sync_api import expect

# Visibility
expect(page.locator(".element")).to_be_visible()
expect(page.locator(".element")).to_be_hidden()

# Content
expect(page.locator("h1")).to_have_text("Expected Text")
expect(page.locator(".alert")).to_contain_text("Success")

# Count
assert page.locator(".item").count() == 5

# URL
assert "/alerts/map/" in page.url
```

### Taking Screenshots

```python
# Manual screenshot
page.screenshot(path="tests/e2e/screenshots/debug.png")

# Full page
page.screenshot(path="screenshot.png", full_page=True)

# Specific element
page.locator("#map").screenshot(path="map.png")
```

---

## Troubleshooting

### Database Permission Error
```
ERROR: permission denied to create database
```

**Solution:**
```sql
ALTER USER nrc_admin CREATEDB;
```

### Browser Not Found
```
ERROR: Browser was not installed
```

**Solution:**
```bash
uv run playwright install chromium
```

### Async/Sync Error
```
SynchronousOnlyOperation: You cannot call this from an async context
```

**Solution:** Already handled in `conftest.py` with `DJANGO_ALLOW_ASYNC_UNSAFE`

### Timeout Errors
```
TimeoutError: Timeout 10000ms exceeded
```

**Solutions:**
- Increase timeout: `page.wait_for_selector("#map", timeout=30000)`
- Check if element exists: `if page.locator("#map").count() > 0:`
- Ensure Django server is running
- Ensure frontend assets are built

### Static Files Not Found
```
404: /static/dist/main.js
```

**Solution:**
```bash
# Build frontend assets first
npm run build

# Or collect static files
uv run python manage.py collectstatic --noinput
```

---

## Best Practices

### ✅ DO
- Use `expect()` for assertions (better error messages)
- Wait for elements before interacting
- Use data attributes for test selectors (`[data-testid="submit"]`)
- Keep tests independent (don't rely on test order)
- Use fixtures for common setup
- Take screenshots on failure for debugging

### ❌ DON'T
- Use fixed `sleep()` delays (use `wait_for_*` instead)
- Test implementation details (test user behavior)
- Make tests brittle with exact pixel coordinates
- Forget to mark with `@pytest.mark.e2e` and `@pytest.mark.django_db`

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: E2E Tests
on: [push, pull_request]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgis/postgis:16-3.4
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s

    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync
          uv run playwright install chromium
          uv run playwright install-deps chromium

      - name: Run migrations
        run: uv run python manage.py migrate

      - name: Build frontend
        run: npm run build

      - name: Run E2E tests
        run: uv run pytest tests/e2e/ -m e2e --video on

      - uses: actions/upload-artifact@v3
        if: failure()
        with:
          name: test-results
          path: test-results/
```

---

## Performance

| Mode | Time | Status |
|------|------|--------|
| Sequential | 68s | ✅ All pass |
| Parallel (-n 4) | 51s | ✅ All pass (16% faster) |

**Recommendation**: Use `-n 4` for faster execution.

## Next Steps

1. **Run Tests** - `uv run pytest tests/e2e/ -n 4`
2. **Add More Tests** - Expand coverage for critical workflows
3. **CI Integration** - Add to GitHub Actions/GitLab CI
4. **Visual Regression** - Add screenshot comparison tests

---

## Resources

- **Playwright Docs:** https://playwright.dev/python/
- **pytest-playwright:** https://github.com/microsoft/playwright-pytest
- **pytest-django:** https://pytest-django.readthedocs.io/
- **Testing Strategy:** [../TESTING_STRATEGY.md](../TESTING_STRATEGY.md)

---

**Total E2E Tests:** 21 tests across 3 files (100% passing)

**Coverage:**
- ✅ Authentication flows (6 tests)
- ✅ Alert map workflows (7 tests)
- ✅ Data pipeline map (8 tests)
- ✅ Filtering and interactions
- ✅ Responsive design
- ✅ Navigation

**Performance:** 51s with parallel execution (-n 4)
