"""Admin interface for data pipeline models."""

from django.contrib import admin, messages
from django.utils.html import format_html
from modeltranslation.admin import TranslationAdmin

from .models import Source, TaskStatistics, Variable, VariableData


@admin.register(Source)
class SourceAdmin(TranslationAdmin):
    """Admin interface for Source model."""

    list_display = ["name", "type", "variable_count", "created_at"]
    list_filter = ["type", "created_at"]
    search_fields = ["name", "description", "class_name"]
    actions = ["remove_all_source_data", "remove_all_data_globally"]

    fieldsets = (
        ("Basic Information", {"fields": ("name", "description", "type", "class_name")}),
        ("URLs", {"fields": ("info_url", "base_url"), "classes": ("collapse",)}),
        ("Additional Info", {"fields": ("comment",), "classes": ("collapse",)}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    readonly_fields = ["created_at", "updated_at"]

    def variable_count(self, obj):
        """Display count of variables for this source."""
        return obj.variables.count()

    variable_count.short_description = "Variables"

    def remove_all_source_data(self, request, queryset):
        """Remove all VariableData records for selected sources."""
        total_deleted = 0
        sources_processed = []

        for source in queryset:
            # Count data records before deletion
            data_count = VariableData.objects.filter(variable__source=source).count()

            # Delete all data for this source
            deleted_count, _ = VariableData.objects.filter(variable__source=source).delete()
            total_deleted += deleted_count
            sources_processed.append(f"{source.name} ({deleted_count:,} records)")

        if total_deleted > 0:
            self.message_user(
                request, f"Successfully removed {total_deleted:,} data records from {len(sources_processed)} source(s): {', '.join(sources_processed)}", messages.SUCCESS
            )
        else:
            self.message_user(request, "No data records found to remove for the selected sources.", messages.INFO)

    remove_all_source_data.short_description = "🗑️ Remove all data for selected sources"

    def remove_all_data_globally(self, request, queryset):
        """Remove all VariableData records from the entire system."""
        total_count = VariableData.objects.count()

        if total_count == 0:
            self.message_user(request, "No data records found in the system.", messages.INFO)
            return

        # Delete all data records
        deleted_count, _ = VariableData.objects.all().delete()

        self.message_user(request, f"⚠️ GLOBAL DATA REMOVAL: Successfully removed all {deleted_count:,} data records from the entire system.", messages.WARNING)

    remove_all_data_globally.short_description = "⚠️ Remove ALL data from entire system"


@admin.register(Variable)
class VariableAdmin(TranslationAdmin):
    """Admin interface for Variable model."""

    list_display = ["code", "name", "source", "type", "period", "adm_level", "data_count"]
    list_filter = ["source", "type", "period", "adm_level", "created_at"]
    search_fields = ["code", "name", "text", "source__name"]
    actions = ["remove_variable_data", "remove_all_data_globally"]

    fieldsets = (
        ("Basic Information", {"fields": ("source", "name", "code", "type")}),
        ("Data Characteristics", {"fields": ("period", "adm_level", "text")}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    readonly_fields = ["created_at", "updated_at"]

    def data_count(self, obj):
        """Display count of data records for this variable."""
        return obj.data_records.count()

    data_count.short_description = "Data Records"

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("source")

    def remove_variable_data(self, request, queryset):
        """Remove all VariableData records for selected variables."""
        total_deleted = 0
        variables_processed = []

        for variable in queryset:
            # Count data records before deletion
            data_count = variable.data_records.count()

            # Delete all data for this variable
            deleted_count, _ = variable.data_records.all().delete()
            total_deleted += deleted_count
            variables_processed.append(f"{variable.code} ({deleted_count:,} records)")

        if total_deleted > 0:
            self.message_user(
                request, f"Successfully removed {total_deleted:,} data records from {len(variables_processed)} variable(s): {', '.join(variables_processed)}", messages.SUCCESS
            )
        else:
            self.message_user(request, "No data records found to remove for the selected variables.", messages.INFO)

    remove_variable_data.short_description = "🗑️ Remove data for selected variables"

    def remove_all_data_globally(self, request, queryset):
        """Remove all VariableData records from the entire system."""
        total_count = VariableData.objects.count()

        if total_count == 0:
            self.message_user(request, "No data records found in the system.", messages.INFO)
            return

        # Delete all data records
        deleted_count, _ = VariableData.objects.all().delete()

        self.message_user(request, f"⚠️ GLOBAL DATA REMOVAL: Successfully removed all {deleted_count:,} data records from the entire system.", messages.WARNING)

    remove_all_data_globally.short_description = "⚠️ Remove ALL data from entire system"


@admin.register(VariableData)
class VariableDataAdmin(admin.ModelAdmin):
    """Admin interface for VariableData model."""

    list_display = ["variable_code", "gid_display", "period", "date_range", "value_display", "text_preview"]
    list_filter = ["variable", "period", "adm_level", "end_date", "variable__source", "variable__type"]
    search_fields = ["variable__code", "variable__name", "gid__geo_id", "gid__name", "text"]
    actions = ["remove_selected_data", "remove_all_data_globally"]

    fieldsets = (
        ("Variable & Location", {"fields": ("variable", "gid", "adm_level")}),
        ("Time Period", {"fields": ("start_date", "end_date", "period")}),
        ("Data", {"fields": ("value", "text")}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    readonly_fields = ["created_at", "updated_at"]

    def variable_code(self, obj):
        """Display variable code."""
        return obj.variable.code

    variable_code.short_description = "Variable Code"

    def gid_display(self, obj):
        """Display location geo_id and name."""
        return f"{obj.gid.geo_id} ({obj.gid.name})"

    gid_display.short_description = "Location"

    def date_range(self, obj):
        """Display date range."""
        if obj.start_date == obj.end_date:
            return obj.start_date.strftime("%Y-%m-%d")
        return f"{obj.start_date.strftime('%Y-%m-%d')} to {obj.end_date.strftime('%Y-%m-%d')}"

    date_range.short_description = "Date Range"

    def value_display(self, obj):
        """Display value with formatting."""
        if obj.value is None:
            return "-"
        return f"{obj.value:,.2f}" if obj.value != int(obj.value) else f"{int(obj.value):,}"

    value_display.short_description = "Value"

    def text_preview(self, obj):
        """Display text preview."""
        if not obj.text:
            return "-"
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text

    text_preview.short_description = "Text Preview"

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("variable", "variable__source", "gid", "adm_level")

    def remove_selected_data(self, request, queryset):
        """Remove selected VariableData records."""
        count = queryset.count()

        if count == 0:
            self.message_user(request, "No data records selected for removal.", messages.INFO)
            return

        # Group by variable for better reporting
        variables_affected = {}
        for record in queryset:
            var_code = record.variable.code
            if var_code not in variables_affected:
                variables_affected[var_code] = 0
            variables_affected[var_code] += 1

        # Delete selected records
        deleted_count, _ = queryset.delete()

        # Create summary message
        var_summary = ", ".join([f"{code} ({count})" for code, count in variables_affected.items()])

        self.message_user(request, f"Successfully removed {deleted_count:,} selected data records from variables: {var_summary}", messages.SUCCESS)

    remove_selected_data.short_description = "🗑️ Remove selected data records"

    def remove_all_data_globally(self, request, queryset):
        """Remove all VariableData records from the entire system."""
        total_count = VariableData.objects.count()

        if total_count == 0:
            self.message_user(request, "No data records found in the system.", messages.INFO)
            return

        # Delete all data records
        deleted_count, _ = VariableData.objects.all().delete()

        self.message_user(request, f"⚠️ GLOBAL DATA REMOVAL: Successfully removed all {deleted_count:,} data records from the entire system.", messages.WARNING)

    remove_all_data_globally.short_description = "⚠️ Remove ALL data from entire system"


@admin.register(TaskStatistics)
class TaskStatisticsAdmin(admin.ModelAdmin):
    """Admin interface for TaskStatistics model."""

    list_display = ["date", "total_tasks_display", "success_rate_display", "avg_duration_display", "max_duration_display"]
    list_filter = ["date"]

    fieldsets = (
        ("Date", {"fields": ("date",)}),
        ("Task Counts", {"fields": ("check_updates_count", "download_data_count", "process_data_count", "full_pipeline_count", "reprocess_data_count")}),
        ("Success/Failure", {"fields": ("success_count", "failure_count", "retry_count")}),
        ("Performance", {"fields": ("avg_duration_seconds", "max_duration_seconds")}),
        ("Computed Fields", {"fields": ("total_tasks", "success_rate"), "classes": ("collapse",)}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    readonly_fields = ["total_tasks", "success_rate", "created_at", "updated_at"]

    def total_tasks_display(self, obj):
        """Display total tasks."""
        return obj.total_tasks

    total_tasks_display.short_description = "Total Tasks"

    def success_rate_display(self, obj):
        """Display success rate with color coding."""
        rate = obj.success_rate
        if rate is None:
            return "-"

        color = "green" if rate >= 90 else "orange" if rate >= 75 else "red"
        return format_html('<span style="color: {};">{:.1f}%</span>', color, rate)

    success_rate_display.short_description = "Success Rate"

    def avg_duration_display(self, obj):
        """Display average duration in human-readable format."""
        if obj.avg_duration_seconds is None:
            return "-"

        duration = obj.avg_duration_seconds
        if duration < 60:
            return f"{duration:.1f}s"
        elif duration < 3600:
            return f"{duration / 60:.1f}m"
        else:
            return f"{duration / 3600:.1f}h"

    avg_duration_display.short_description = "Avg Duration"

    def max_duration_display(self, obj):
        """Display maximum duration in human-readable format."""
        if obj.max_duration_seconds is None:
            return "-"

        duration = obj.max_duration_seconds
        if duration < 60:
            return f"{duration:.1f}s"
        elif duration < 3600:
            return f"{duration / 60:.1f}m"
        else:
            return f"{duration / 3600:.1f}h"

    max_duration_display.short_description = "Max Duration"
