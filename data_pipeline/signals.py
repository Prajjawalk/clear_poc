"""Django signals for data pipeline events."""

import django.dispatch

# Signal sent when data processing completes successfully for a source
# Provides: sender (source class), source (Source instance), variables_processed (dict), success_count (int)
data_processing_completed = django.dispatch.Signal()

# Signal sent when data is available for a specific variable
# Provides: sender (variable class), variable (Variable instance), source (Source instance)
variable_data_updated = django.dispatch.Signal()