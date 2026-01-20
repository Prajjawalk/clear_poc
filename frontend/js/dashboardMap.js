import L from 'leaflet'
import chroma from 'chroma-js'
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
export class DashboardMap {
    constructor(containerId, options = {}) {
        this.containerId = containerId
        this.options = {
            center: [15.5007, 32.5599],
            zoom: 6,
            ...options
        }
        this.map = null
        this.choroplethLayers = {}
        this.activeChoroplethLayer = null
        this.choroplethData = {}
        this.themesConfig = {}
        this.colorScales = {}

        this.initializeMap()
        this.addLegendControl()
        this.bindEvents()
    }

    setThemesConfig(themesConfig) {
        // """Load themes configuration and initialize color scales."""
        this.themesConfig = themesConfig

        // Initialize color scales dynamically from themes
        themesConfig.forEach(theme => {
            theme.variables.forEach(variable => {
                const minVal = variable.min_value !== null ? variable.min_value : 0
                const maxVal = variable.max_value !== null ? variable.max_value : 100

                // Handle both named and custom colormaps
                let colorScale
                if (theme.colormap.type === 'named') {
                    // Use named ColorBrewer scheme
                    colorScale = chroma.scale(theme.colormap.value)
                } else {
                    // Use custom two-color scale
                    colorScale = chroma.scale(theme.colormap.value)
                }

                this.colorScales[variable.code] = colorScale.domain([minVal, maxVal])
            })
        })
    }

    initializeMap() {
        // Initialize map centered on Sudan
        this.map = L.map(this.containerId).setView(this.options.center, this.options.zoom)

        // Add tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 18
        }).addTo(this.map)
    }

    addLegendControl() {
        // Create legend control
        const legend = L.control({ position: 'bottomright' })

        legend.onAdd = () => {
            const div = L.DomUtil.create('div', 'map-legend')
            div.id = 'map-legend'
            div.style.display = 'none' // Hidden by default
            return div
        }

        legend.addTo(this.map)
        this.legendControl = legend
    }

    updateLegend(varCode) {
        // Find the theme and variable for this code
        let theme = null
        let variable = null

        for (const t of this.themesConfig) {
            const v = t.variables.find(v => v.code === varCode)
            if (v) {
                theme = t
                variable = v
                break
            }
        }

        if (!theme || !variable || !theme.colorbar_url) {
            console.log(theme, variable, theme.colorbar_url)
            this.hideLegend()
            return
        }

        const legendDiv = document.getElementById('map-legend')
        if (!legendDiv) return

        // Build legend HTML with colorbar image
        const minValue = variable.min_value !== null ? variable.min_value : 0
        const maxValue = variable.max_value !== null ? variable.max_value : 100

        legendDiv.innerHTML = `
            <div class="legend-header">
                <strong>${variable.name}</strong>
            </div>
            <div class="legend-colorbar">
                <img src="${theme.colorbar_url}" alt="Color scale" />
            </div>
            <div class="legend-scale">
                <span class="legend-min">${minValue}</span>
                <span class="legend-max">${maxValue}</span>
            </div>
            <div class="legend-unit">${variable.unit || ''}</div>
        `

        legendDiv.style.display = 'block'
    }

    hideLegend() {
        const legendDiv = document.getElementById('map-legend')
        if (legendDiv) {
            legendDiv.style.display = 'none'
        }
    }

    setChoroplethData(data) {
        this.choroplethData = data
        this.initializeChoroplethLayers()
    }

    initializeChoroplethLayers() {
        // Create Leaflet GeoJSON layers for each choropleth variable
        for (const [code, layerData] of Object.entries(this.choroplethData)) {
            const layer = L.geoJSON(layerData.geojson, {
                style: (feature) => this.getChoroplethStyle(feature, code),
                onEachFeature: (feature, layer) => {
                    layer.bindPopup(this.createChoroplethPopup(feature, layerData))
                }
            })

            this.choroplethLayers[code] = {
                layer: layer,
                data: layerData
            }
        }
    }

    getChoroplethStyle(feature, varCode) {
        const value = feature.properties.value
        let fillColor = '#cccccc'
        let fillOpacity = 0.7

        // Use dynamic color scales from themes configuration
        if (this.colorScales[varCode]) {
            fillColor = this.colorScales[varCode](value).hex()
            fillOpacity = value === 0 ? 0.2 : 0.7
        }

        return {
            fillColor: fillColor,
            fillOpacity: fillOpacity,
            color: '#666',
            weight: 1,
            opacity: 0.8
        }
    }

    createChoroplethPopup(feature, layerData) {
        const props = feature.properties
        let valueDisplay = props.value

        // Format value based on variable type
        if (layerData.code === 'fewsnet_food_insecurity') {
            const ipcPhases = {
                1: 'Minimal',
                2: 'Stressed',
                3: 'Crisis',
                4: 'Emergency',
                5: 'Famine'
            }
            valueDisplay = `Phase ${props.value}: ${ipcPhases[Math.floor(props.value)]}`
        } else if (layerData.unit === 'people') {
            valueDisplay = `${Math.round(props.value).toLocaleString()} ${layerData.unit}`
        } else {
            valueDisplay = `${props.value} ${layerData.unit}`
        }

        return `
            <div class="choropleth-popup">
                <div class="popup-title">${props.name}</div>
                <div class="popup-meta">
                    <strong>${layerData.name}</strong>
                </div>
                <div class="popup-value">${valueDisplay}</div>
                <div class="popup-date">
                    <small>Data from: ${new Date(props.end_date).toLocaleDateString()}</small>
                </div>
            </div>
        `
    }

    showChoroplethLayer(varCode) {
        // Hide current active layer(s)
        if (this.activeChoroplethLayer && this.choroplethLayers[this.activeChoroplethLayer]) {
            this.map.removeLayer(this.choroplethLayers[this.activeChoroplethLayer].layer)
        }

        // Hide combined layers if they exist
        if (this.combinedLayers) {
            this.combinedLayers.forEach(layer => this.map.removeLayer(layer))
            this.combinedLayers = null
        }

        // Check if this is a combined layer (ends with _combined)
        if (varCode.endsWith('_combined')) {
            const themeCode = varCode.replace('_combined', '')
            const theme = this.themesConfig.find(t => t.code === themeCode)
            if (theme) {
                const variableCodes = theme.variables.map(v => v.code)
                this.showCombinedRiskLayer(variableCodes, theme)
                this.activeChoroplethLayer = varCode
                this.hideLegend()  // Hide legend for combined layers
            }
        }
        // Show single layer
        else if (this.choroplethLayers[varCode]) {
            this.choroplethLayers[varCode].layer.addTo(this.map)
            this.activeChoroplethLayer = varCode
            this.updateLegend(varCode)  // Show legend for single variable
        }
    }

    showCombinedRiskLayer(layerCodes, theme) {
        // Create combined layer by overlaying all variables with configured opacity
        this.combinedLayers = []

        layerCodes.forEach(code => {
            if (this.choroplethLayers[code]) {

                const combinedLayer = L.geoJSON(this.choroplethLayers[code].data.geojson, {
                    style: (feature) => {
                        const baseStyle = this.getChoroplethStyle(feature, code)
                        return {
                            ...baseStyle,
                            fillOpacity: 0.25,  // 25% opacity for all layers
                            opacity: 0.5
                        }
                    },
                    onEachFeature: (feature, layer) => {
                        layer.bindPopup(this.createCombinedPopup(feature, layerCodes))
                    }
                })
                combinedLayer.addTo(this.map)
                this.combinedLayers.push(combinedLayer)
            }
        })
    }

    createCombinedPopup(feature, layerCodes) {
        const props = feature.properties
        let content = `<div class="choropleth-popup"><div class="popup-title">${props.name}</div>`

        // Add all risk indicators
        layerCodes.forEach(code => {
            if (this.choroplethLayers[code]) {
                const layerData = this.choroplethLayers[code].data
                const layerFeature = this.findFeatureByLocation(layerData.geojson, props.name)

                if (layerFeature) {
                    const value = layerFeature.properties.value
                    let valueDisplay = value

                    if (code === 'fewsnet_food_insecurity') {
                        const ipcPhases = {1: 'Minimal', 2: 'Stressed', 3: 'Crisis', 4: 'Emergency', 5: 'Famine'}
                        valueDisplay = `Phase ${Math.floor(value)}: ${ipcPhases[Math.floor(value)]}`
                    } else if (layerData.unit === 'people') {
                        valueDisplay = `${Math.round(value).toLocaleString()} ${layerData.unit}`
                    } else {
                        valueDisplay = `${value} ${layerData.unit}`
                    }

                    content += `<div class="popup-meta mt-2"><strong>${layerData.name}:</strong> ${valueDisplay}</div>`
                }
            }
        })

        content += `</div>`
        return content
    }

    findFeatureByLocation(geojson, locationName) {
        return geojson.features.find(f => f.properties.name === locationName)
    }

    hideChoroplethLayers() {
        // Hide all choropleth layers
        for (const code of Object.keys(this.choroplethLayers)) {
            if (this.choroplethLayers[code]) {
                this.map.removeLayer(this.choroplethLayers[code].layer)
            }
        }

        // Hide combined layers if they exist
        if (this.combinedLayers) {
            this.combinedLayers.forEach(layer => this.map.removeLayer(layer))
            this.combinedLayers = null
        }

        this.activeChoroplethLayer = null
        this.hideLegend()  // Hide legend when no layer is active
    }


    bindEvents() {
        // Choropleth layer toggle
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('choropleth-layer-toggle')) {
                const value = e.target.value
                if (value === 'none') {
                    this.hideChoroplethLayers()
                } else {
                    this.showChoroplethLayer(value)
                }
            }
        })
    }
}

// Initialize alert map when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const mapContainer = document.getElementById('dashboard-map')
    if (mapContainer) {
        // Get alert data from template context
        const dashboardDataElement = document.getElementById('dashboard-data')
        let dashboardData = []

        if (dashboardDataElement) {
            try {
                dashboardData = JSON.parse(dashboardDataElement.textContent)
            } catch (e) {
                console.error('Failed to parse map data:', e)
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

        // Get choropleth data from template context
        const choroplethDataElement = document.getElementById('choropleth-data')
        let choroplethData = {}

        if (choroplethDataElement) {
            try {
                choroplethData = JSON.parse(choroplethDataElement.textContent)
            } catch (e) {
                console.error('Failed to parse choropleth data:', e)
            }
        }

        // Get themes configuration from template context
        const themesConfigElement = document.getElementById('themes-config')
        let themesConfig = []

        if (themesConfigElement) {
            try {
                themesConfig = JSON.parse(themesConfigElement.textContent)
            } catch (e) {
                console.error('Failed to parse themes config:', e)
            }
        }

        // Initialize the map
        const dashboardMap = new DashboardMap('dashboard-map')
        dashboardMap.setThemesConfig(themesConfig)
        dashboardMap.setChoroplethData(choroplethData)

        // Make map available globally for debugging
        window.dashboardMap = dashboardMap
    }
})
