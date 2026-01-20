// Data Pipeline Map module with Leaflet and MarkerCluster
import L from 'leaflet';
import 'leaflet.markercluster';
// CSS imported in main.scss

// Fix Leaflet icon paths - using Vite public directory
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: '/static/dist/leaflet/images/marker-icon-2x.png',
    iconUrl: '/static/dist/leaflet/images/marker-icon.png',
    shadowUrl: '/static/dist/leaflet/images/marker-shadow.png',
});

class DataPipelineMap {
    constructor() {
        this.map = null;
        this.markerClusterGroup = null;
        this.markersLayer = null;
        this.currentData = null;
        this.usesClustering = true;
        this.sourceColors = {};
        this.colorPalette = [
            '#e41a1c', '#377eb8', '#4daf4a', '#984ea3',
            '#ff7f00', '#ffff33', '#a65628', '#f781bf',
            '#999999', '#66c2a5', '#fc8d62', '#8da0cb'
        ];
        this.clusterColor = '#6b46c1'; // Purple for clusters, distinct from source colors

        console.log('Initializing DataPipelineMap...');
        this.initializeMap();
        this.bindEvents();
        this.loadInitialData();
        console.log('DataPipelineMap initialization complete');
    }

    initializeMap() {
        console.log('Initializing Leaflet map...');
        // Initialize map centered on Sudan
        this.map = L.map('map').setView([15.5007, 32.5599], 6);

        // Add base layers
        const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 18
        });

        const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles © Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
            maxZoom: 18
        });

        // Add default layer
        osmLayer.addTo(this.map);

        // Layer control
        const baseLayers = {
            "OpenStreetMap": osmLayer,
            "Satellite": satelliteLayer
        };
        L.control.layers(baseLayers).addTo(this.map);

        // Initialize marker cluster group (if available)
        if (typeof L.markerClusterGroup !== 'undefined') {
            this.markerClusterGroup = L.markerClusterGroup({
                chunkedLoading: true,
                spiderfyOnMaxZoom: false,
                showCoverageOnHover: false,
                zoomToBoundsOnClick: true,
                iconCreateFunction: (cluster) => {
                    const count = cluster.getChildCount();
                    let size = 'small';
                    let sizeValue = 30;
                    if (count > 100) {
                        size = 'large';
                        sizeValue = 50;
                    } else if (count > 10) {
                        size = 'medium';
                        sizeValue = 40;
                    }

                    // Create gradient background for clusters
                    const gradientId = `cluster-gradient-${size}`;
                    const opacity = 0.6 + (count > 100 ? 0.3 : count > 10 ? 0.2 : 0.1);

                    return new L.DivIcon({
                        html: `<div style="background: ${this.clusterColor}; opacity: ${opacity}; width: ${sizeValue}px; height: ${sizeValue}px; border-radius: 50%; display: flex; align-items: center; justify-content: center; border: 2px solid white; box-shadow: 0 2px 5px rgba(0,0,0,0.3);"><span style="color: white; font-weight: bold; font-size: ${size === 'large' ? '16px' : size === 'medium' ? '14px' : '12px'};">${count}</span></div>`,
                        className: '',
                        iconSize: new L.Point(sizeValue, sizeValue)
                    });
                }
            });
            console.log('Using MarkerCluster for markers');
            this.map.addLayer(this.markerClusterGroup);
        } else {
            console.log('MarkerCluster not available, using regular layer group');
            this.markerClusterGroup = null;
            this.usesClustering = false;

            // Hide clustering button since it's not available
            const clusteringBtn = document.getElementById('toggleClustering');
            if (clusteringBtn) {
                clusteringBtn.style.display = 'none';
            }
        }

        this.markersLayer = L.layerGroup();
        if (!this.markerClusterGroup) {
            this.map.addLayer(this.markersLayer);
        }
    }

    bindEvents() {
        // Filter form submission
        document.getElementById('mapFilters').addEventListener('submit', (e) => {
            e.preventDefault();
            this.loadMapData();
        });

        // Reset filters
        document.getElementById('resetFilters').addEventListener('click', () => {
            this.resetFilters();
        });

        // Zoom to data
        document.getElementById('zoomToData').addEventListener('click', () => {
            this.zoomToData();
        });

        // Toggle clustering
        document.getElementById('toggleClustering').addEventListener('click', () => {
            this.toggleClustering();
        });

        // Fullscreen toggle
        document.getElementById('fullscreenMap').addEventListener('click', () => {
            this.toggleFullscreen();
        });

        // Source filter change
        document.getElementById('sourceSelect').addEventListener('change', (e) => {
            this.filterVariablesBySource(e.target.value);
        });
    }

    filterVariablesBySource(sourceId) {
        const variableSelect = document.getElementById('variableSelect');
        const variables = JSON.parse(document.getElementById('variables-data').textContent);

        // Clear current options
        variableSelect.innerHTML = '<option value="">{% trans "All Variables" %}</option>';

        // Filter variables by source
        const filteredVariables = sourceId ?
            variables.filter(v => v.source.id == sourceId) :
            variables;

        // Add filtered options
        filteredVariables.forEach(variable => {
            const option = document.createElement('option');
            option.value = variable.id;
            option.textContent = `${variable.name} (${variable.source.name})`;
            variableSelect.appendChild(option);
        });
    }

    async loadMapData() {
        console.log('Loading map data from API...');
        this.showLoading(true);

        try {
            const formData = new FormData(document.getElementById('mapFilters'));
            const params = new URLSearchParams();

            for (const [key, value] of formData.entries()) {
                if (value) params.append(key, value);
            }

            const response = await fetch(`/pipeline/api/map-data/?${params}`);
            const data = await response.json();
            console.log('API response:', data);

            if (data.success) {
                console.log(`Received ${data.total_features} features from API`);
                this.currentData = data.data;
                this.displayMapData(data.data);
                this.updateDataInfo(data);
                this.updateLegend(data.data);
            } else {
                console.error('API returned error:', data.error);
                this.showError(data.error || 'Failed to load map data');
            }
        } catch (error) {
            console.error('Error loading map data:', error);
            this.showError('Network error occurred while loading data');
        } finally {
            this.showLoading(false);
        }
    }

    displayMapData(geojsonData) {
        // Clear existing markers
        if (this.markerClusterGroup) {
            this.markerClusterGroup.clearLayers();
        }
        this.markersLayer.clearLayers();

        if (!geojsonData.features || geojsonData.features.length === 0) {
            this.showEmptyState(true);
            return;
        }

        this.showEmptyState(false);

        // Build source colors mapping
        this.buildSourceColors(geojsonData);

        // Create markers
        geojsonData.features.forEach(feature => {
            const { geometry, properties } = feature;
            const [lng, lat] = geometry.coordinates;

            // Determine marker color based on source
            const color = this.getSourceColor(properties.source_name);

            // Create custom icon
            const icon = L.divIcon({
                className: 'custom-marker',
                html: `<div style="background: ${color}; width: 16px; height: 16px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });

            // Create popup content
            const popupContent = this.createPopupContent(properties);

            // Create marker
            const marker = L.marker([lat, lng], { icon })
                .bindPopup(popupContent);

            // Add to appropriate layer
            if (this.usesClustering && this.markerClusterGroup) {
                this.markerClusterGroup.addLayer(marker);
            } else {
                this.markersLayer.addLayer(marker);
            }
        });

        // Add non-clustered layer to map if needed
        if (!this.usesClustering && !this.map.hasLayer(this.markersLayer)) {
            this.map.addLayer(this.markersLayer);
        }

        // Zoom to data bounds
        if (geojsonData.features.length > 0) {
            this.zoomToData();
        }
    }

    buildSourceColors(geojsonData) {
        // Reset source colors
        this.sourceColors = {};

        // Get unique sources
        const sources = [...new Set(geojsonData.features.map(f => f.properties.source_name))];

        // Assign colors to sources
        sources.forEach((source, index) => {
            this.sourceColors[source] = this.colorPalette[index % this.colorPalette.length];
        });
    }

    getSourceColor(sourceName) {
        return this.sourceColors[sourceName] || '#999999'; // Default gray if source not found
    }

    createPopupContent(properties) {
        const formatValue = (value) => {
            if (typeof value === 'number') {
                return value.toLocaleString();
            }
            return value || 'N/A';
        };

        return `
            <div class="popup-content">
                <h6 class="popup-title">${properties.location_name}</h6>
                <div class="popup-details">
                    <strong>${properties.variable_name}</strong><br>
                    <span class="text-muted">${properties.source_name}</span><br><br>
                    <strong>Value:</strong> ${formatValue(properties.value)} ${properties.unit}<br>
                    <strong>Records:</strong> ${properties.record_count}<br>
                    <strong>Date:</strong> ${properties.latest_date}<br>
                    <strong>Admin Level:</strong> ${properties.admin_level}
                </div>
            </div>
        `;
    }

    updateDataInfo(apiResponse) {
        const infoContainer = document.getElementById('dataInfo');
        if (infoContainer) {
            const { total_features, filters } = apiResponse;

            let filterText = 'All data';
            if (filters.source_id || filters.variable_id || filters.start_date || filters.end_date) {
                const parts = [];
                if (filters.source_id) parts.push('filtered by source');
                if (filters.variable_id) parts.push('filtered by variable');
                if (filters.start_date || filters.end_date) parts.push('filtered by date');
                filterText = parts.join(', ');
            }

            infoContainer.innerHTML = `
                <small class="text-muted">
                    Showing ${total_features} location${total_features !== 1 ? 's' : ''} (${filterText})
                </small>
            `;
        }
    }

    updateLegend(geojsonData) {
        const legend = document.getElementById('mapLegend');
        const content = document.getElementById('legendContent');

        if (!legend || !content) {
            console.warn('Legend elements not found');
            return;
        }

        if (!geojsonData.features || geojsonData.features.length === 0) {
            legend.style.display = 'none';
            return;
        }

        let legendItems = '';

        // Add source colors to legend
        const sources = Object.keys(this.sourceColors).sort();
        if (sources.length > 0) {
            legendItems += '<div style="margin-bottom: 10px;"><strong>Data Sources</strong></div>';
            sources.forEach(source => {
                const color = this.sourceColors[source];
                legendItems += `
                    <div class="legend-item">
                        <div class="legend-color" style="background: ${color};"></div>
                        <span>${source}</span>
                    </div>
                `;
            });
        }

        // Add cluster indicator if clustering is enabled
        if (this.usesClustering && this.markerClusterGroup) {
            legendItems += '<div style="margin-top: 10px; margin-bottom: 5px;"><strong>Clusters</strong></div>';
            legendItems += `
                <div class="legend-item">
                    <div class="legend-color" style="background: ${this.clusterColor}; opacity: 0.7;"></div>
                    <span>Multiple points</span>
                </div>
            `;
        }

        content.innerHTML = legendItems;
        legend.style.display = 'block';
    }

    toggleClustering() {
        // Don't toggle if clustering is not available
        if (!this.markerClusterGroup) {
            console.log('Clustering not available (MarkerCluster plugin not loaded)');
            return;
        }

        this.usesClustering = !this.usesClustering;

        if (this.usesClustering) {
            this.map.removeLayer(this.markersLayer);
            this.map.addLayer(this.markerClusterGroup);
        } else {
            this.map.removeLayer(this.markerClusterGroup);
            this.map.addLayer(this.markersLayer);
        }

        // Re-display current data
        if (this.currentData) {
            this.displayMapData(this.currentData);
        }

        // Update button appearance
        const button = document.getElementById('toggleClustering');
        if (this.usesClustering) {
            button.classList.remove('btn-primary');
            button.classList.add('btn-outline-secondary');
        } else {
            button.classList.remove('btn-outline-secondary');
            button.classList.add('btn-primary');
        }
    }

    toggleFullscreen() {
        const mapContainer = document.getElementById('mapContainer');

        if (!document.fullscreenElement) {
            mapContainer.requestFullscreen().then(() => {
                this.map.invalidateSize();
            });
        } else {
            document.exitFullscreen().then(() => {
                this.map.invalidateSize();
            });
        }
    }

    zoomToData() {
        if (!this.currentData || !this.currentData.features || this.currentData.features.length === 0) {
            return;
        }

        const group = new L.featureGroup();
        this.currentData.features.forEach(feature => {
            const [lng, lat] = feature.geometry.coordinates;
            L.marker([lat, lng]).addTo(group);
        });

        this.map.fitBounds(group.getBounds(), { padding: [20, 20] });
    }

    resetFilters() {
        document.getElementById('sourceSelect').value = '';
        document.getElementById('variableSelect').value = '';
        document.getElementById('startDate').value = '';
        document.getElementById('endDate').value = '';
        document.getElementById('aggregation').value = 'latest';
        this.filterVariablesBySource('');
        this.loadMapData();
    }

    loadInitialData() {
        console.log('Loading initial data...');
        this.loadMapData();
    }

    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        overlay.style.display = show ? 'flex' : 'none';
    }

    showEmptyState(show) {
        const emptyState = document.getElementById('emptyState');
        emptyState.style.display = show ? 'block' : 'none';
    }

    showError(message) {
        // Create a temporary alert
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger alert-dismissible fade show';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        // Insert at top of map container
        const mapContainer = document.getElementById('mapContainer');
        mapContainer.insertBefore(alertDiv, mapContainer.firstChild);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}

// Export for testing and global access
export { DataPipelineMap };
window.DataPipelineMap = DataPipelineMap;

// Auto-initialize if map container exists
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, checking for map...');

    const mapContainer = document.getElementById('map');
    if (mapContainer) {
        console.log('Map container found, initializing DataPipelineMap');
        new DataPipelineMap();
    }
});