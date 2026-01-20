/**
 * Vitest setup file - runs before each test file
 */

import { vi } from 'vitest';

// Mock Leaflet globally since it requires a real DOM
global.L = {
  map: vi.fn(() => ({
    setView: vi.fn(() => ({
      addLayer: vi.fn(),
      removeLayer: vi.fn(),
      hasLayer: vi.fn(() => false),
      fitBounds: vi.fn(),
      invalidateSize: vi.fn(),
      getCenter: vi.fn(() => ({ lat: 15.5007, lng: 32.5599 })),
      getZoom: vi.fn(() => 6),
    })),
    getCenter: vi.fn(() => ({ lat: 15.5007, lng: 32.5599 })),
    getZoom: vi.fn(() => 6),
    addLayer: vi.fn(),
    removeLayer: vi.fn(),
    hasLayer: vi.fn(() => false),
    fitBounds: vi.fn(),
    invalidateSize: vi.fn(),
  })),
  tileLayer: vi.fn(() => ({
    addTo: vi.fn(),
  })),
  layerGroup: vi.fn(() => ({
    addTo: vi.fn(),
    clearLayers: vi.fn(),
    addLayer: vi.fn(),
    removeLayer: vi.fn(),
    getLayers: vi.fn(() => []),
  })),
  featureGroup: vi.fn(() => ({
    addTo: vi.fn(),
    getBounds: vi.fn(() => ({
      isValid: vi.fn(() => true),
    })),
  })),
  marker: vi.fn(() => ({
    addTo: vi.fn(),
    bindPopup: vi.fn(),
    setIcon: vi.fn(),
  })),
  divIcon: vi.fn((options) => options),
  control: {
    layers: vi.fn(() => ({
      addTo: vi.fn(),
    })),
  },
  Control: {
    extend: vi.fn((config) => {
      return function() {
        this.onAdd = config.onAdd;
        this.options = config.options || {};
      };
    }),
  },
  DomUtil: {
    create: vi.fn((tag, className) => {
      const el = document.createElement(tag);
      if (className) el.className = className;
      return el;
    }),
  },
  DomEvent: {
    on: vi.fn(),
    stopPropagation: vi.fn(),
    preventDefault: vi.fn(),
    disableClickPropagation: vi.fn(),
  },
  Icon: {
    Default: {
      prototype: {
        _getIconUrl: vi.fn(),
      },
      mergeOptions: vi.fn(),
    },
  },
  markerClusterGroup: vi.fn(() => ({
    addTo: vi.fn(),
    clearLayers: vi.fn(),
    addLayer: vi.fn(),
    removeLayer: vi.fn(),
    getLayers: vi.fn(() => []),
  })),
};

// Mock window.bootstrap (Bootstrap JS)
global.bootstrap = {
  Tooltip: vi.fn((el) => ({ dispose: vi.fn() })),
  Popover: vi.fn((el) => ({ dispose: vi.fn() })),
  Alert: vi.fn((el) => ({ close: vi.fn() })),
};

// Setup DOM environment
beforeEach(() => {
  // Reset document body
  document.body.innerHTML = '';

  // Mock fetch globally
  global.fetch = vi.fn();

  // Mock console methods to reduce noise in tests
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  // Clean up mocks
  vi.restoreAllMocks();
  vi.clearAllMocks();
});
