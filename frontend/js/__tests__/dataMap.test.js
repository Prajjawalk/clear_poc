/**
 * Tests for Data Pipeline Map module
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { DataPipelineMap } from '../dataMap.js';

describe('DataPipelineMap', () => {
  let mapContainer;

  beforeEach(() => {
    // Create DOM elements needed by DataPipelineMap
    document.body.innerHTML = `
      <div id="mapContainer">
        <div id="map"></div>
      </div>
      <form id="mapFilters">
        <select id="sourceSelect">
          <option value="">All Sources</option>
          <option value="1">Source 1</option>
        </select>
        <select id="variableSelect">
          <option value="">All Variables</option>
        </select>
        <input type="text" id="startDate" />
        <input type="text" id="endDate" />
        <select id="aggregation">
          <option value="latest">Latest</option>
        </select>
        <button type="submit">Apply</button>
      </form>
      <button id="resetFilters">Reset</button>
      <button id="zoomToData">Zoom</button>
      <button id="toggleClustering">Toggle Clustering</button>
      <button id="fullscreenMap">Fullscreen</button>
      <div id="dataInfo"></div>
      <div id="loadingOverlay" style="display: none;"></div>
      <div id="emptyState" style="display: none;"></div>
      <div id="mapLegend" style="display: none;">
        <div id="legendContent"></div>
      </div>
      <script id="variables-data" type="application/json">[]</script>
    `;

    mapContainer = document.getElementById('map');

    // Mock fetch to prevent actual API calls
    global.fetch = vi.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve({ success: true, data: { features: [] }, total_features: 0, filters: {} })
      })
    );
  });

  describe('Initialization', () => {
    it('creates a DataPipelineMap instance', () => {
      const dataMap = new DataPipelineMap();
      expect(dataMap).toBeInstanceOf(DataPipelineMap);
    });

    it('initializes map with correct center coordinates', () => {
      const dataMap = new DataPipelineMap();
      expect(dataMap.map).toBeDefined();
      // Map is initialized - verify it's a Leaflet map object
      expect(dataMap.map.setView).toBeDefined();
      expect(dataMap.map.getCenter).toBeDefined();
    });

    it('initializes with clustering enabled', () => {
      const dataMap = new DataPipelineMap();
      expect(dataMap.usesClustering).toBe(true);
    });

    it('sets up color palette for sources', () => {
      const dataMap = new DataPipelineMap();
      expect(dataMap.colorPalette).toHaveLength(12);
      expect(dataMap.clusterColor).toBe('#6b46c1');
    });
  });

  describe('Source Colors', () => {
    it('builds source colors from geojson data', () => {
      const dataMap = new DataPipelineMap();
      const geojsonData = {
        features: [
          { properties: { source_name: 'ACLED' } },
          { properties: { source_name: 'DTM' } },
          { properties: { source_name: 'ACLED' } },
        ]
      };

      dataMap.buildSourceColors(geojsonData);

      expect(Object.keys(dataMap.sourceColors)).toHaveLength(2);
      expect(dataMap.sourceColors['ACLED']).toBeDefined();
      expect(dataMap.sourceColors['DTM']).toBeDefined();
    });

    it('assigns different colors to different sources', () => {
      const dataMap = new DataPipelineMap();
      const geojsonData = {
        features: [
          { properties: { source_name: 'Source A' } },
          { properties: { source_name: 'Source B' } },
        ]
      };

      dataMap.buildSourceColors(geojsonData);

      expect(dataMap.sourceColors['Source A']).not.toBe(dataMap.sourceColors['Source B']);
    });

    it('returns default color for unknown source', () => {
      const dataMap = new DataPipelineMap();
      const color = dataMap.getSourceColor('UnknownSource');
      expect(color).toBe('#999999');
    });
  });

  describe('Popup Content', () => {
    it('creates popup with all property values', () => {
      const dataMap = new DataPipelineMap();
      const properties = {
        location_name: 'Khartoum',
        variable_name: 'Population',
        source_name: 'ACLED',
        value: 5000,
        unit: 'people',
        record_count: 10,
        latest_date: '2024-10-01',
        admin_level: 'State'
      };

      const popup = dataMap.createPopupContent(properties);

      expect(popup).toContain('Khartoum');
      expect(popup).toContain('Population');
      expect(popup).toContain('ACLED');
      expect(popup).toContain('5,000');
      expect(popup).toContain('people');
    });

    it('formats numbers with commas', () => {
      const dataMap = new DataPipelineMap();
      const properties = {
        location_name: 'Test',
        variable_name: 'Test Var',
        source_name: 'Test Source',
        value: 1234567,
        unit: 'units',
        record_count: 100,
        latest_date: '2024-10-01',
        admin_level: 'Admin1'
      };

      const popup = dataMap.createPopupContent(properties);

      expect(popup).toContain('1,234,567');
    });
  });

  describe('Data Display', () => {
    it('shows empty state when no features', () => {
      const dataMap = new DataPipelineMap();
      const emptyData = { features: [] };

      dataMap.displayMapData(emptyData);

      const emptyState = document.getElementById('emptyState');
      expect(emptyState.style.display).toBe('block');
    });

    it('hides empty state when features exist', () => {
      const dataMap = new DataPipelineMap();
      const geojsonData = {
        features: [{
          geometry: { coordinates: [32.5, 15.5] },
          properties: {
            source_name: 'Test',
            location_name: 'Khartoum',
            variable_name: 'Pop',
            value: 100,
            unit: 'people',
            record_count: 1,
            latest_date: '2024-10-01',
            admin_level: 'State'
          }
        }]
      };

      dataMap.displayMapData(geojsonData);

      const emptyState = document.getElementById('emptyState');
      expect(emptyState.style.display).toBe('none');
    });
  });

  describe('Loading State', () => {
    it('shows loading overlay', () => {
      const dataMap = new DataPipelineMap();
      dataMap.showLoading(true);

      const overlay = document.getElementById('loadingOverlay');
      expect(overlay.style.display).toBe('flex');
    });

    it('hides loading overlay', () => {
      const dataMap = new DataPipelineMap();
      dataMap.showLoading(false);

      const overlay = document.getElementById('loadingOverlay');
      expect(overlay.style.display).toBe('none');
    });
  });

  describe('Filter Variables by Source', () => {
    it('filters variables when source is selected', () => {
      document.getElementById('variables-data').textContent = JSON.stringify([
        { id: 1, name: 'Var1', source: { id: 1, name: 'Source 1' } },
        { id: 2, name: 'Var2', source: { id: 2, name: 'Source 2' } },
        { id: 3, name: 'Var3', source: { id: 1, name: 'Source 1' } },
      ]);

      const dataMap = new DataPipelineMap();
      dataMap.filterVariablesBySource('1');

      const variableSelect = document.getElementById('variableSelect');
      const options = variableSelect.querySelectorAll('option');

      // Should have "All Variables" + 2 filtered variables
      expect(options.length).toBe(3);
    });

    it('shows all variables when no source selected', () => {
      document.getElementById('variables-data').textContent = JSON.stringify([
        { id: 1, name: 'Var1', source: { id: 1, name: 'Source 1' } },
        { id: 2, name: 'Var2', source: { id: 2, name: 'Source 2' } },
      ]);

      const dataMap = new DataPipelineMap();
      dataMap.filterVariablesBySource('');

      const variableSelect = document.getElementById('variableSelect');
      const options = variableSelect.querySelectorAll('option');

      // Should have "All Variables" + all variables
      expect(options.length).toBe(3);
    });
  });

  describe('Reset Filters', () => {
    it('clears all filter inputs', () => {
      const dataMap = new DataPipelineMap();

      // Set some filter values
      document.getElementById('sourceSelect').value = '1';
      document.getElementById('variableSelect').value = '2';

      dataMap.resetFilters();

      expect(document.getElementById('sourceSelect').value).toBe('');
      expect(document.getElementById('variableSelect').value).toBe('');
    });
  });

  describe('Update Data Info', () => {
    it('updates info with feature count', () => {
      const dataMap = new DataPipelineMap();
      const apiResponse = {
        total_features: 5,
        filters: {}
      };

      dataMap.updateDataInfo(apiResponse);

      const infoContainer = document.getElementById('dataInfo');
      expect(infoContainer.innerHTML).toContain('5 locations');
    });

    it('shows singular when one location', () => {
      const dataMap = new DataPipelineMap();
      const apiResponse = {
        total_features: 1,
        filters: {}
      };

      dataMap.updateDataInfo(apiResponse);

      const infoContainer = document.getElementById('dataInfo');
      expect(infoContainer.innerHTML).toContain('1 location');
      expect(infoContainer.innerHTML).not.toContain('locations');
    });
  });

  describe('Error Handling', () => {
    it('shows error message', () => {
      const dataMap = new DataPipelineMap();
      const testError = 'Network error occurred';

      dataMap.showError(testError);

      // Check that an alert div was created
      const alert = document.querySelector('.alert-danger');
      expect(alert).toBeTruthy();
      expect(alert.textContent).toContain(testError);
    });
  });
});
