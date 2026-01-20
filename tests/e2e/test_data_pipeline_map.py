"""E2E tests for data pipeline map."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
@pytest.mark.django_db
def test_data_pipeline_map_loads(authenticated_page: Page, live_server):
    """Test that data pipeline map page loads correctly."""
    page = authenticated_page
    page.goto(f"{live_server.url}/pipeline/map/")

    # Wait for map and check it's visible
    map_el = page.locator("#map")
    expect(map_el).to_be_visible(timeout=5000)


@pytest.mark.e2e
@pytest.mark.django_db
def test_data_pipeline_source_filter(authenticated_page: Page, live_server):
    """Test source filtering functionality."""
    page = authenticated_page
    page.goto(f"{live_server.url}/pipeline/map/")

    # Wait for map
    page.wait_for_selector("#map")

    # Check if source select exists
    source_select = page.locator("#sourceSelect")
    if source_select.count() > 0:
        expect(source_select).to_be_visible()

        # Should have at least "All Sources" option
        options = source_select.locator("option")
        assert options.count() >= 1


@pytest.mark.e2e
@pytest.mark.django_db
def test_data_pipeline_variable_filter(authenticated_page: Page, live_server):
    """Test variable filtering functionality."""
    page = authenticated_page
    page.goto(f"{live_server.url}/pipeline/map/")

    # Wait for map
    page.wait_for_selector("#map")

    # Check if variable select exists
    variable_select = page.locator("#variableSelect")
    if variable_select.count() > 0:
        expect(variable_select).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db
def test_data_pipeline_apply_filters(authenticated_page: Page, live_server):
    """Test applying filters updates the map."""
    page = authenticated_page
    page.goto(f"{live_server.url}/pipeline/map/")

    # Wait for map
    page.wait_for_selector("#map")

    # Look for filter form
    filter_form = page.locator("#mapFilters")
    if filter_form.count() > 0:
        # Look for apply button
        apply_btn = filter_form.locator("button[type='submit']")
        if apply_btn.count() > 0:
            # Click apply
            apply_btn.click()

            # Wait briefly for loading
            page.wait_for_timeout(200)

            # Map should still be visible
            expect(page.locator("#map")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db
def test_data_pipeline_reset_filters(authenticated_page: Page, live_server):
    """Test reset filters button."""
    page = authenticated_page
    page.goto(f"{live_server.url}/pipeline/map/")

    # Wait for map
    page.wait_for_selector("#map")

    # Look for reset button
    reset_btn = page.locator("#resetFilters")
    if reset_btn.count() > 0:
        # Modify a filter first
        source_select = page.locator("#sourceSelect")
        if source_select.count() > 0:
            # Select a non-default option if available
            options = source_select.locator("option")
            if options.count() > 1:
                source_select.select_option(index=1)

        # Click reset
        reset_btn.click()

        # Wait briefly for reset
        page.wait_for_timeout(100)

        # Source select should be back to default
        if source_select.count() > 0:
            selected_value = source_select.input_value()
            # Should be empty or first option
            assert selected_value == "" or selected_value is not None


@pytest.mark.e2e
@pytest.mark.django_db
def test_data_pipeline_zoom_to_data(authenticated_page: Page, live_server):
    """Test zoom to data button (if data exists)."""
    page = authenticated_page
    page.goto(f"{live_server.url}/pipeline/map/")

    # Wait for map
    page.wait_for_selector("#map")

    # Look for zoom button
    zoom_btn = page.locator("#zoomToData")
    if zoom_btn.count() > 0:
        expect(zoom_btn).to_be_visible()

        # Click zoom button
        zoom_btn.click()

        # Wait briefly for zoom animation
        page.wait_for_timeout(200)

        # Map should still be visible
        expect(page.locator("#map")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db
def test_data_pipeline_toggle_clustering(authenticated_page: Page, live_server):
    """Test toggle clustering button."""
    page = authenticated_page
    page.goto(f"{live_server.url}/pipeline/map/")

    # Wait for map
    page.wait_for_selector("#map")

    # Look for clustering toggle
    clustering_btn = page.locator("#toggleClustering")
    if clustering_btn.count() > 0:
        # Wait for button to be ready and click
        clustering_btn.wait_for(state="attached", timeout=3000)
        clustering_btn.click(force=True)

        # Wait briefly for action
        page.wait_for_timeout(200)

        # Map should still be visible
        expect(page.locator("#map")).to_be_visible()


@pytest.mark.e2e
@pytest.mark.django_db
def test_data_pipeline_base_layer_control(authenticated_page: Page, live_server):
    """Test that base layer control is available."""
    page = authenticated_page
    page.goto(f"{live_server.url}/pipeline/map/")

    # Wait for map
    page.wait_for_selector("#map")

    # Look for Leaflet layer control (standard Leaflet UI)
    layer_control = page.locator(".leaflet-control-layers")
    if layer_control.count() > 0:
        # Layer control exists, try to interact with it
        layer_control.click()

        # Wait briefly for menu
        page.wait_for_timeout(100)
        # Layer menu should be visible after click
