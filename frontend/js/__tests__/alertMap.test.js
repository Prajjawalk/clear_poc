/**
 * Tests for Alert Map module
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { AlertMap } from '../alertMap.js';

describe('AlertMap', () => {
  beforeEach(() => {
    // Create DOM elements needed by AlertMap
    document.body.innerHTML = `
      <div id="alert-map"></div>
      <div id="alert-count">0</div>
      <div id="last-updated"></div>
      <div id="mapLegendContent"></div>
      <button id="apply-filters">Apply</button>
      <button id="reset-filters">Reset</button>
      <button id="fullscreen-btn">Fullscreen</button>
      <input type="checkbox" class="shock-type-filter" value="1" checked />
      <input type="checkbox" class="shock-type-filter" value="2" checked />
      <input type="checkbox" class="severity-filter" value="1" checked />
      <input type="checkbox" class="severity-filter" value="5" checked />
      <input type="checkbox" id="show-all" checked />
      <input type="checkbox" id="show-all-severity" checked />
      <input type="date" id="date-from" />
      <input type="date" id="date-to" />
      <script id="alert-data" type="application/json">[]</script>
      <script id="shock-types-config" type="application/json">{}</script>
    `;
  });

  describe('Initialization', () => {
    it('creates an AlertMap instance', () => {
      const alertMap = new AlertMap('alert-map');
      expect(alertMap).toBeInstanceOf(AlertMap);
    });

    it('initializes with default options', () => {
      const alertMap = new AlertMap('alert-map');
      expect(alertMap.options.center).toEqual([15.5007, 32.5599]);
      expect(alertMap.options.zoom).toBe(6);
    });

    it('accepts custom options', () => {
      const customOptions = {
        center: [10, 20],
        zoom: 8
      };
      const alertMap = new AlertMap('alert-map', customOptions);
      expect(alertMap.options.center).toEqual([10, 20]);
      expect(alertMap.options.zoom).toBe(8);
    });

    it('initializes alert data as empty array', () => {
      const alertMap = new AlertMap('alert-map');
      expect(alertMap.alertData).toEqual([]);
    });
  });

  describe('Shock Type Configuration', () => {
    it('sets shock type configuration', () => {
      const alertMap = new AlertMap('alert-map');
      const shockTypes = {
        'Conflict': { icon: '⚔️', color: '#ff0000' },
        'Flood': { icon: '🌊', color: '#0000ff' }
      };

      alertMap.setShockTypeConfig(shockTypes);

      expect(alertMap.shockTypesConfig).toEqual(shockTypes);
      expect(alertMap.alertTypePictograms['Conflict']).toBe('⚔️');
      expect(alertMap.alertTypePictograms['Flood']).toBe('🌊');
    });
  });

  describe('Alert Icon Creation', () => {
    it('creates icon with correct severity size', () => {
      const alertMap = new AlertMap('alert-map');
      const alert = {
        severity: 5,
        shock_type: { name: 'Conflict', icon: '⚔️' }
      };

      const icon = alertMap.createAlertIcon(alert);

      expect(icon.options.className).toContain('severity-5');
      expect(icon.options.iconSize).toEqual([36, 36]);
    });

    it('creates smaller icon for low severity', () => {
      const alertMap = new AlertMap('alert-map');
      const alert = {
        severity: 1,
        shock_type: { name: 'Conflict', icon: '⚔️' }
      };

      const icon = alertMap.createAlertIcon(alert);

      expect(icon.options.className).toContain('severity-1');
      expect(icon.options.iconSize).toEqual([20, 20]);
    });

    it('uses default icon when shock type icon missing', () => {
      const alertMap = new AlertMap('alert-map');
      const alert = {
        severity: 3,
        shock_type: { name: 'Unknown' }
      };

      const icon = alertMap.createAlertIcon(alert);

      expect(icon.options.html).toContain('📍');
    });
  });

  describe('Popup Content', () => {
    it('creates popup with alert details', () => {
      const alertMap = new AlertMap('alert-map');
      const alert = {
        id: 1,
        title: 'Test Alert',
        text: 'This is a test alert with some long text that should be truncated',
        shock_type: { name: 'Conflict', css_class: 'bg-conflict' },
        severity: 4,
        valid_until: '2024-12-31'
      };

      const popup = alertMap.createPopupContent(alert);

      expect(popup).toContain('Test Alert');
      expect(popup).toContain('Conflict');
      expect(popup).toContain('Severity 4');
      expect(popup).toContain('data-alert-id="1"');
    });

    it('truncates long alert text', () => {
      const alertMap = new AlertMap('alert-map');
      const longText = 'a'.repeat(200);
      const alert = {
        id: 1,
        title: 'Test',
        text: longText,
        shock_type: { name: 'Conflict', css_class: 'bg-conflict' },
        severity: 3,
        valid_until: '2024-12-31'
      };

      const popup = alertMap.createPopupContent(alert);

      expect(popup).toContain('...');
      expect(popup).not.toContain(longText);
    });
  });

  describe('Alert Filtering', () => {
    it('filters by shock type', () => {
      const alertMap = new AlertMap('alert-map');
      const alert = {
        shock_type: { id: 1, name: 'Conflict' },
        severity: 3,
        shock_date: '2024-10-01',
        locations: []
      };

      // Only type "2" is checked
      document.querySelector('.shock-type-filter[value="1"]').checked = false;
      document.querySelector('.shock-type-filter[value="2"]').checked = true;

      expect(alertMap.shouldShowAlert(alert)).toBe(false);
    });

    it('filters by severity', () => {
      const alertMap = new AlertMap('alert-map');
      const alert = {
        shock_type: { id: 1 },
        severity: 3,
        shock_date: '2024-10-01',
        locations: []
      };

      // Only severity "1" and "5" are checked
      document.querySelector('.severity-filter[value="1"]').checked = true;
      document.querySelector('.severity-filter[value="5"]').checked = true;

      expect(alertMap.shouldShowAlert(alert)).toBe(false);
    });

    it('filters by date range', () => {
      const alertMap = new AlertMap('alert-map');
      const alert = {
        shock_type: { id: 1 },
        severity: 3,
        shock_date: '2024-10-15',
        locations: []
      };

      document.getElementById('date-from').value = '2024-10-01';
      document.getElementById('date-to').value = '2024-10-10';

      expect(alertMap.shouldShowAlert(alert)).toBe(false);
    });

    it('shows alert when all filters pass', () => {
      const alertMap = new AlertMap('alert-map');
      const alert = {
        shock_type: { id: 1 },
        severity: 1,
        shock_date: '2024-10-15',
        locations: []
      };

      document.getElementById('date-from').value = '2024-10-01';
      document.getElementById('date-to').value = '2024-10-31';

      expect(alertMap.shouldShowAlert(alert)).toBe(true);
    });
  });

  describe('Reset Filters', () => {
    it('checks all filter checkboxes', () => {
      const alertMap = new AlertMap('alert-map');

      // Uncheck some filters
      document.querySelector('.shock-type-filter[value="1"]').checked = false;
      document.querySelector('.severity-filter[value="1"]').checked = false;

      alertMap.resetFilters();

      expect(document.querySelector('.shock-type-filter[value="1"]').checked).toBe(true);
      expect(document.querySelector('.severity-filter[value="1"]').checked).toBe(true);
    });

    it('clears date filters', () => {
      const alertMap = new AlertMap('alert-map');

      document.getElementById('date-from').value = '2024-10-01';
      document.getElementById('date-to').value = '2024-10-31';

      alertMap.resetFilters();

      expect(document.getElementById('date-from').value).toBe('');
      expect(document.getElementById('date-to').value).toBe('');
    });

    it('checks show-all checkboxes', () => {
      const alertMap = new AlertMap('alert-map');

      document.getElementById('show-all').checked = false;
      document.getElementById('show-all-severity').checked = false;

      alertMap.resetFilters();

      expect(document.getElementById('show-all').checked).toBe(true);
      expect(document.getElementById('show-all-severity').checked).toBe(true);
    });
  });

  describe('Update Alert Count', () => {
    it('updates alert count element', () => {
      const alertMap = new AlertMap('alert-map');

      // Ensure filters allow these alerts through
      document.querySelector('.shock-type-filter[value="1"]').checked = true;
      document.querySelector('.shock-type-filter[value="2"]').checked = true;
      document.querySelector('.severity-filter[value="1"]').checked = true;

      const alerts = [
        {
          id: 1,
          title: 'Conflict Alert',
          text: 'This is a conflict alert',
          shock_type: { id: 1, name: 'Conflict', css_class: 'bg-conflict' },
          severity: 3,
          shock_date: '2024-10-01',
          valid_until: '2024-12-31',
          locations: [{ point: { coordinates: [32.5, 15.5] } }]
        },
        {
          id: 2,
          title: 'Flood Alert',
          text: 'This is a flood alert',
          shock_type: { id: 2, name: 'Flood', css_class: 'bg-flood' },
          severity: 4,
          shock_date: '2024-10-02',
          valid_until: '2024-12-31',
          locations: [{ point: { coordinates: [33.5, 16.5] } }]
        }
      ];

      // Add checkboxes for severities 3 and 4
      const severity3 = document.createElement('input');
      severity3.type = 'checkbox';
      severity3.className = 'severity-filter';
      severity3.value = '3';
      severity3.checked = true;
      document.body.appendChild(severity3);

      const severity4 = document.createElement('input');
      severity4.type = 'checkbox';
      severity4.className = 'severity-filter';
      severity4.value = '4';
      severity4.checked = true;
      document.body.appendChild(severity4);

      alertMap.updateMapMarkers(alerts);

      const countElement = document.getElementById('alert-count');
      expect(countElement.textContent).toBe('2');
    });
  });

  describe('Legend Update', () => {
    it('updates legend with shock type config', () => {
      const alertMap = new AlertMap('alert-map');
      const legendContent = document.getElementById('mapLegendContent');

      alertMap.setShockTypeConfig({
        'Conflict': { icon: '⚔️' },
        'Flood': { icon: '🌊' }
      });

      alertMap.updateLegendContent(legendContent);

      expect(legendContent.innerHTML).toContain('⚔️');
      expect(legendContent.innerHTML).toContain('🌊');
      expect(legendContent.innerHTML).toContain('Conflict');
      expect(legendContent.innerHTML).toContain('Flood');
    });

    it('includes severity levels in legend', () => {
      const alertMap = new AlertMap('alert-map');
      const legendContent = document.getElementById('mapLegendContent');

      alertMap.updateLegendContent(legendContent);

      expect(legendContent.innerHTML).toContain('Low (1)');
      expect(legendContent.innerHTML).toContain('Critical (5)');
    });
  });

  describe('Alert Data Management', () => {
    it('sets alert data', () => {
      const alertMap = new AlertMap('alert-map');
      const alerts = [
        {
          id: 1,
          title: 'Alert 1',
          text: 'Alert 1 text',
          shock_type: { id: 1, name: 'Conflict', css_class: 'bg-conflict' },
          severity: 3,
          shock_date: '2024-10-01',
          valid_until: '2024-12-31',
          locations: []
        },
        {
          id: 2,
          title: 'Alert 2',
          text: 'Alert 2 text',
          shock_type: { id: 2, name: 'Flood', css_class: 'bg-flood' },
          severity: 4,
          shock_date: '2024-10-02',
          valid_until: '2024-12-31',
          locations: []
        }
      ];

      alertMap.setAlertData(alerts);

      expect(alertMap.alertData).toEqual(alerts);
    });
  });
});
