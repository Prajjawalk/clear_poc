// Alert Framework JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    $('[data-toggle="tooltip"]').tooltip();

    // Auto-refresh for dashboard
    if (window.location.pathname.includes('alert_framework')) {
        // Refresh page every 5 minutes for dashboard
        if (window.location.pathname.endsWith('/')) {
            setTimeout(function() {
                window.location.reload();
            }, 5 * 60 * 1000); // 5 minutes
        }
    }

    // Detection action handlers
    $('.detection-action-btn').on('click', function(e) {
        e.preventDefault();
        var $btn = $(this);
        var action = $btn.data('action');
        var detectionId = $btn.data('detection-id');
        var originalId = $btn.data('original-id');

        // Show confirmation for destructive actions
        if (action === 'dismiss' || action === 'mark_duplicate') {
            var message = action === 'dismiss' 
                ? 'Are you sure you want to dismiss this detection?' 
                : 'Are you sure you want to mark this as duplicate?';
            
            if (!confirm(message)) {
                return;
            }
        }

        // Show loading state
        $btn.addClass('loading').prop('disabled', true);

        // Make AJAX request
        $.ajax({
            url: `/alert_framework/detections/${detectionId}/action/`,
            method: 'POST',
            data: {
                action: action,
                original_id: originalId,
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val()
            },
            success: function(response) {
                if (response.success) {
                    // Update status badge
                    var $statusBadge = $btn.closest('tr').find('.status-badge');
                    $statusBadge.removeClass('badge-warning badge-success badge-secondary')
                               .addClass('badge-' + (response.new_status === 'processed' ? 'success' : 'secondary'))
                               .text(response.new_status.charAt(0).toUpperCase() + response.new_status.slice(1));

                    // Show success message
                    showAlert('success', response.message);

                    // Hide action buttons for processed/dismissed detections
                    if (response.new_status !== 'pending') {
                        $btn.closest('.action-buttons').hide();
                    }
                } else {
                    showAlert('error', response.error || 'Action failed');
                }
            },
            error: function(xhr) {
                var error = xhr.responseJSON ? xhr.responseJSON.error : 'Action failed';
                showAlert('error', error);
            },
            complete: function() {
                $btn.removeClass('loading').prop('disabled', false);
            }
        });
    });

    // Detector run handlers
    $('.run-detector-btn').on('click', function(e) {
        e.preventDefault();
        var $btn = $(this);
        var $form = $btn.closest('form');

        // Show confirmation
        if (!confirm('Start detector execution?')) {
            return;
        }

        // Show loading state
        $btn.addClass('loading').prop('disabled', true);
        $btn.html('<i class="bi bi-hourglass-split"></i> Running...');

        // Submit form normally (will redirect with message)
        $form.submit();
    });

    // Auto-update detection status
    function updateDetectionStatuses() {
        $('.detection-row[data-status="pending"]').each(function() {
            var $row = $(this);
            var detectionId = $row.data('detection-id');
            
            // Check if detection status has changed
            $.get(`/alert_framework/detections/${detectionId}/`, function(data) {
                // This would require an API endpoint that returns JSON
                // For now, we'll just refresh the page if needed
            });
        });
    }

    // Update statuses every 30 seconds on detection list page
    if (window.location.pathname.includes('detections')) {
        setInterval(updateDetectionStatuses, 30000);
    }

    // Filter form auto-submit on change
    $('.auto-submit').on('change', function() {
        $(this).closest('form').submit();
    });

    // Confidence score styling
    $('.confidence-score').each(function() {
        var $elem = $(this);
        var score = parseFloat($elem.text());
        
        if (score >= 0.7) {
            $elem.addClass('confidence-high');
        } else if (score >= 0.4) {
            $elem.addClass('confidence-medium');
        } else {
            $elem.addClass('confidence-low');
        }
    });

    // Template preview
    $('.template-preview-btn').on('click', function(e) {
        e.preventDefault();
        var templateId = $(this).data('template-id');
        
        $.get(`/alert_framework/templates/${templateId}/preview/`, function(data) {
            var $modal = $('#template-preview-modal');
            $modal.find('.modal-body').html(data);
            $modal.modal('show');
        });
    });
});

// Utility function to show alerts
function showAlert(type, message) {
    var alertClass = type === 'success' ? 'alert-success' : 'alert-danger';
    var alertHtml = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="close" data-dismiss="alert">
                <span>&times;</span>
            </button>
        </div>
    `;
    
    // Insert at top of main content
    $('main').prepend(alertHtml);
    
    // Auto-dismiss after 5 seconds
    setTimeout(function() {
        $('.alert').alert('close');
    }, 5000);
}

// Format detection timestamps
function formatTimestamp(timestamp) {
    var date = new Date(timestamp);
    var now = new Date();
    var diff = now - date;
    var seconds = Math.floor(diff / 1000);
    var minutes = Math.floor(seconds / 60);
    var hours = Math.floor(minutes / 60);
    var days = Math.floor(hours / 24);

    if (days > 0) {
        return `${days} day${days > 1 ? 's' : ''} ago`;
    } else if (hours > 0) {
        return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    } else if (minutes > 0) {
        return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    } else {
        return 'Just now';
    }
}

// Export for use in other scripts
window.AlertFramework = {
    showAlert: showAlert,
    formatTimestamp: formatTimestamp
};