import L from 'leaflet'
// CSS imported in main.scss

// Fix Leaflet marker icon paths - using Vite public directory
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconUrl: '/static/dist/leaflet/images/marker-icon.png',
    iconRetinaUrl: '/static/dist/leaflet/images/marker-icon-2x.png',
    shadowUrl: '/static/dist/leaflet/images/marker-shadow.png',
    iconSize: [15, 25],         // Default is [25, 41] - making it 60% smaller
    iconAnchor: [7, 25],        // Default is [12, 41] - adjusted proportionally
    popupAnchor: [1, -22],      // Default is [1, -34] - adjusted proportionally
    shadowSize: [25, 25],       // Default is [41, 41] - keeping shadow proportional
    shadowAnchor: [6, 25]       // Default is [12, 41] - adjusted proportionally
});

// Alert Map Module
export class AlertMap {
    constructor(containerId, options = {}) {
        this.containerId = containerId
        this.options = {
            center: [15.5007, 32.5599],
            zoom: 6,
            ...options
        }
        this.map = null
        this.alertMarkers = null
        this.alertData = []

        this.initializeMap()
        this.addLegendControl()
        this.bindEvents()
    }

    initializeMap() {
        // Initialize map centered on Sudan
        this.map = L.map(this.containerId).setView(this.options.center, this.options.zoom)

        // Add tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 18
        }).addTo(this.map)

        // Store markers and layers
        this.alertMarkers = L.layerGroup().addTo(this.map)

        // Alert type pictograms mapping - will be set dynamically from backend data
        this.alertTypePictograms = {}

        console.log('AlertMap initialized with pictograms:', this.alertTypePictograms)

        // Severity size mapping
        this.severitySizes = {
            1: [20, 20],
            2: [24, 24],
            3: [28, 28],
            4: [32, 32],
            5: [36, 36]
        }
    }

    setShockTypeConfig(shockTypesConfig) {
        // Set dynamic shock type configuration
        this.shockTypesConfig = shockTypesConfig
        this.alertTypePictograms = {}
        
        for (const [name, config] of Object.entries(shockTypesConfig)) {
            this.alertTypePictograms[name] = config.icon
        }
        
        console.log('Shock type configuration updated:', this.alertTypePictograms)
    }

    createAlertIcon(alert) {
        const shockTypeName = alert.shock_type.name
        const iconSymbol = alert.shock_type.icon || this.alertTypePictograms[shockTypeName] || '📍'
        const iconSize = this.severitySizes[alert.severity] || this.severitySizes[1]

        console.log('Creating icon for:', shockTypeName, 'with symbol:', iconSymbol)

        return L.divIcon({
            className: `custom-alert-marker-dot severity-${alert.severity}`,
            html: `
                <div class="alert-marker-background"></div>
                <span class="alert-marker-icon">${iconSymbol}</span>
            `,
            iconSize: iconSize,
            iconAnchor: [iconSize[0] / 2, iconSize[1] / 2]
        })
    }

    addLegendControl() {
        // Create custom legend control
        const self = this // Store reference to AlertMap instance
        const LegendControl = L.Control.extend({
            options: {
                position: 'bottomright'
            },

            onAdd: function(map) {
                const container = L.DomUtil.create('div', 'leaflet-legend-control leaflet-bar')

                // Create toggle button (mobile) and legend content
                const toggleBtn = L.DomUtil.create('a', 'legend-toggle-btn d-lg-none', container)
                toggleBtn.href = '#'
                toggleBtn.title = 'Toggle Legend'
                toggleBtn.innerHTML = '<i class="bi bi-info-circle"></i>'

                // Create legend content container
                const legendContent = L.DomUtil.create('div', 'map-legend d-none d-lg-block', container)
                legendContent.id = 'mapLegendContent'

                // Add legend content - this will be updated dynamically
                self.updateLegendContent(legendContent)

                // Handle toggle button click
                L.DomEvent.on(toggleBtn, 'click', function(e) {
                    L.DomEvent.stopPropagation(e)
                    L.DomEvent.preventDefault(e)

                    // Toggle legend visibility on mobile
                    if (legendContent.classList.contains('d-none')) {
                        legendContent.classList.remove('d-none')
                        legendContent.classList.add('d-lg-block')
                        toggleBtn.classList.add('legend-active')
                    } else {
                        legendContent.classList.add('d-none')
                        legendContent.classList.remove('d-lg-block')
                        toggleBtn.classList.remove('legend-active')
                    }
                })

                // Prevent map interaction when clicking on legend
                L.DomEvent.disableClickPropagation(container)

                return container
            }
        })

        // Add the control to the map
        this.legendControl = new LegendControl()
        this.legendControl.addTo(this.map)
    }

    updateLegendContent(legendContent) {
        // Generate dynamic legend content based on shock type configuration
        let alertTypesHtml = ''
        
        if (this.shockTypesConfig) {
            for (const [name, config] of Object.entries(this.shockTypesConfig)) {
                alertTypesHtml += `
                    <div class="legend-item">
                        <span class="legend-symbol">${config.icon}</span>
                        <span>${name}</span>
                    </div>
                `
            }
        } else {
            // Fallback to hardcoded values if config not available
            alertTypesHtml = `
                <div class="legend-item">
                    <span class="legend-symbol">📍</span>
                    <span>Loading...</span>
                </div>
            `
        }

        legendContent.innerHTML = `
            <div class="legend-title">
                <i class="bi bi-info-circle me-1"></i>
                Alert Legend
            </div>
            <div class="legend-section">
                <div class="legend-subtitle">Alert Types</div>
                ${alertTypesHtml}
            </div>
            <div class="legend-section">
                <div class="legend-subtitle">Severity Levels</div>
                <div class="legend-item">
                    <div class="legend-severity-dot severity-1" style="width: 12px; height: 12px;"></div>
                    <span>Low (1)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-severity-dot severity-2" style="width: 14px; height: 14px;"></div>
                    <span>Moderate (2)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-severity-dot severity-3" style="width: 16px; height: 16px;"></div>
                    <span>High (3)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-severity-dot severity-4" style="width: 18px; height: 18px;"></div>
                    <span>Very High (4)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-severity-dot severity-5" style="width: 20px; height: 20px;"></div>
                    <span>Critical (5)</span>
                </div>
            </div>
            <div class="legend-note">
                <small>Color and size indicate severity level</small>
            </div>
        `
    }

    setAlertData(data) {
        this.alertData = data
        this.updateMapMarkers(data)
    }

    createPopupContent(alert) {
        const validUntil = new Date(alert.valid_until).toLocaleDateString()
        return `
            <div class="popup-alert-content">
                <div class="popup-alert-title">${alert.title}</div>
                <div class="popup-alert-meta">
                    <span class="badge bg-${alert.shock_type.css_class} text-white me-1">
                        ${alert.shock_type.name}
                    </span>
                    <span class="popup-alert-severity severity-${alert.severity}">
                        Severity ${alert.severity}
                    </span>
                </div>
                <div class="popup-alert-text">${alert.text.substring(0, 150)}...</div>
                <div class="mt-2">
                    <small class="text-muted">
                        <i class="bi bi-calendar3 me-1"></i>
                        Valid until: ${validUntil}
                    </small>
                </div>
                <div class="mt-2">
                    <button class="btn btn-sm btn-primary view-alert-btn" data-alert-id="${alert.id}">
                        <i class="bi bi-eye me-1"></i>
                        View Details
                    </button>
                </div>
            </div>
        `
    }

    updateMapMarkers(alerts) {
        // Clear existing markers
        this.alertMarkers.clearLayers()

        let displayedCount = 0

        alerts.forEach(alert => {
            // Apply filters
            if (!this.shouldShowAlert(alert)) return

            // Create markers for each location
            alert.locations.forEach(location => {
                if (location.point) {
                    const [lng, lat] = location.point.coordinates
                    const marker = L.marker([lat, lng], {
                        icon: this.createAlertIcon(alert)
                    })

                    marker.bindPopup(this.createPopupContent(alert))
                    marker.addTo(this.alertMarkers)
                    displayedCount++
                }
            })
        })

        // Update alert count
        const countElement = document.getElementById('alert-count')
        if (countElement) {
            countElement.textContent = displayedCount
        }

        const lastUpdatedElement = document.getElementById('last-updated')
        if (lastUpdatedElement) {
            lastUpdatedElement.textContent = new Date().toLocaleString()
        }
    }

    shouldShowAlert(alert) {
        // Check shock type filter
        const typeFilters = Array.from(document.querySelectorAll('.shock-type-filter:checked')).map(cb => cb.value)
        if (typeFilters.length > 0 && !typeFilters.includes(alert.shock_type.id.toString())) {
            return false
        }

        // Check severity filter
        const severityFilters = Array.from(document.querySelectorAll('.severity-filter:checked')).map(cb => cb.value)
        if (severityFilters.length > 0 && !severityFilters.includes(alert.severity.toString())) {
            return false
        }

        // Check date filters
        const dateFrom = document.getElementById('date-from')?.value
        const dateTo = document.getElementById('date-to')?.value
        const alertDate = new Date(alert.shock_date)

        if (dateFrom && alertDate < new Date(dateFrom)) return false
        if (dateTo && alertDate > new Date(dateTo)) return false

        return true
    }

    applyFilters() {
        this.updateMapMarkers(this.alertData)
    }

    resetFilters() {
        // Reset all filter checkboxes
        document.querySelectorAll('.shock-type-filter, .severity-filter').forEach(cb => {
            cb.checked = true
        })

        // Clear date filters
        const dateFrom = document.getElementById('date-from')
        const dateTo = document.getElementById('date-to')
        if (dateFrom) dateFrom.value = ''
        if (dateTo) dateTo.value = ''

        // Reset show-all checkboxes
        const showAllType = document.getElementById('show-all')
        const showAllSeverity = document.getElementById('show-all-severity')
        if (showAllType) showAllType.checked = true
        if (showAllSeverity) showAllSeverity.checked = true

        // Refresh markers
        this.updateMapMarkers(this.alertData)
    }

    bindEvents() {
        // Apply filters button
        const applyButton = document.getElementById('apply-filters')
        if (applyButton) {
            applyButton.addEventListener('click', () => this.applyFilters())
        }

        // Reset filters button
        const resetButton = document.getElementById('reset-filters')
        if (resetButton) {
            resetButton.addEventListener('click', () => this.resetFilters())
        }

        // Show all checkboxes
        const showAllType = document.getElementById('show-all')
        if (showAllType) {
            showAllType.addEventListener('change', (e) => {
                document.querySelectorAll('.shock-type-filter').forEach(cb => {
                    cb.checked = e.target.checked
                })
                this.applyFilters()
            })
        }

        const showAllSeverity = document.getElementById('show-all-severity')
        if (showAllSeverity) {
            showAllSeverity.addEventListener('change', (e) => {
                document.querySelectorAll('.severity-filter').forEach(cb => {
                    cb.checked = e.target.checked
                })
                this.applyFilters()
            })
        }

        // Individual filter checkboxes
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('shock-type-filter') ||
                e.target.classList.contains('severity-filter')) {
                this.applyFilters()
            }
        })

        // Fullscreen button
        const fullscreenBtn = document.getElementById('fullscreen-btn')
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', () => {
                const mapContainer = document.getElementById(this.containerId)
                if (mapContainer.requestFullscreen) {
                    mapContainer.requestFullscreen()
                }
                setTimeout(() => {
                    this.map.invalidateSize()
                }, 100)
            })
        }

        // View alert details buttons (delegated event)
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('view-alert-btn') ||
                e.target.closest('.view-alert-btn')) {
                const button = e.target.classList.contains('view-alert-btn') ?
                              e.target : e.target.closest('.view-alert-btn')
                const alertId = button.getAttribute('data-alert-id')
                if (alertId) {
                    window.location.href = `/alerts/alert/${alertId}/`
                }
            }
        })
    }
}

// Initialize alert map when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const mapContainer = document.getElementById('alert-map')
    if (mapContainer) {
        // Get alert data from template context
        const alertDataElement = document.getElementById('alert-data')
        let alertData = []

        if (alertDataElement) {
            try {
                alertData = JSON.parse(alertDataElement.textContent)
            } catch (e) {
                console.error('Failed to parse alert data:', e)
            }
        }
        
        // Get shock types configuration from template context
        const shockTypesConfigElement = document.getElementById('shock-types-config')
        let shockTypesConfig = {}

        if (shockTypesConfigElement) {
            try {
                shockTypesConfig = JSON.parse(shockTypesConfigElement.textContent)
            } catch (e) {
                console.error('Failed to parse shock types config:', e)
            }
        }

        // Initialize the map
        const alertMap = new AlertMap('alert-map')
        alertMap.setShockTypeConfig(shockTypesConfig)
        alertMap.setAlertData(alertData)
        
        // Update legend with dynamic configuration
        const legendContent = document.getElementById('mapLegendContent')
        if (legendContent) {
            alertMap.updateLegendContent(legendContent)
        }

        // Make map available globally for debugging
        window.alertMap = alertMap
    }
})
