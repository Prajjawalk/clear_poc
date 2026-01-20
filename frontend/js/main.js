import * as bootstrap from 'bootstrap'
import '../scss/main.scss'
import './alertMap.js'
import './dashboardMap.js'
import './notifications.js'

// Make bootstrap globally available
window.bootstrap = bootstrap

console.log('Vite is working!')

// Data Pipeline specific JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    })

    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl)
    })

    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)')
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert)
            bsAlert.close()
        }, 5000)
    })

    // Confirm delete actions
    const deleteButtons = document.querySelectorAll('[data-action="delete"]')
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            const confirmed = confirm('Are you sure you want to delete this item? This action cannot be undone.')
            if (!confirmed) {
                e.preventDefault()
            }
        })
    })

    // Auto-refresh dashboard statistics every 30 seconds
    if (document.querySelector('.stat-card')) {
        setInterval(function() {
            // Only refresh if page is visible
            if (!document.hidden) {
                fetch(window.location.pathname)
                    .then(response => response.text())
                    .then(html => {
                        const parser = new DOMParser()
                        const doc = parser.parseFromString(html, 'text/html')
                        
                        // Update stat cards
                        document.querySelectorAll('.stat-card').forEach((card, index) => {
                            const newCard = doc.querySelectorAll('.stat-card')[index]
                            if (newCard) {
                                card.innerHTML = newCard.innerHTML
                            }
                        })
                    })
                    .catch(error => console.log('Dashboard refresh failed:', error))
            }
        }, 30000) // 30 seconds
    }
})
