"""Django admin configuration for alerts models."""

from django import forms
from django.contrib import admin
from modeltranslation.admin import TranslationAdmin

from .models import Alert, EmailTemplate, ShockType, Subscription, UserAlert


class ShockTypeForm(forms.ModelForm):
    """Custom form for ShockType with color picker and emoji picker."""
    
    class Meta:
        model = ShockType
        fields = '__all__'
        widgets = {
            'color': forms.TextInput(attrs={
                'type': 'color',
                'style': 'width: 50px; height: 30px; padding: 0; border: none;'
            }),
            'icon': forms.TextInput(attrs={
                'class': 'emoji-picker-input',
                'style': 'width: 200px;',
                'placeholder': '📍 Click to choose emoji/symbol...'
            }),
        }


@admin.register(ShockType)
class ShockTypeAdmin(TranslationAdmin):
    """Admin configuration for ShockType model."""

    form = ShockTypeForm
    list_display = ["name", "icon", "color", "css_class", "created_at", "updated_at"]
    search_fields = ["name", "name_en", "name_ar", "css_class"]
    readonly_fields = ["created_at", "updated_at", "background_css_class"]

    fieldsets = [
        ("Basic Information", {"fields": ["name"]}),
        ("Display Configuration", {"fields": ["icon", "color", "css_class", "background_css_class"]}),
        ("Metadata", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]


class UserAlertInline(admin.TabularInline):
    """Inline admin for UserAlert model in Alert admin."""
    model = UserAlert
    extra = 0
    readonly_fields = ["created_at", "updated_at", "is_read", "is_rated", "is_flagged"]
    fields = ["user", "rating", "bookmarked", "comment", "flag_false", "flag_incomplete", "received_at"]


@admin.register(Alert)
class AlertAdmin(TranslationAdmin):
    """Admin configuration for Alert model."""

    list_display = ["title", "shock_type", "severity", "shock_date", "go_no_go", "is_active", "created_at"]
    list_filter = ["shock_type", "severity", "go_no_go", "shock_date", "valid_from", "valid_until"]
    search_fields = ["title", "title_en", "title_ar", "text", "text_en", "text_ar"]
    date_hierarchy = "shock_date"
    readonly_fields = ["created_at", "updated_at", "is_active"]
    actions = ["approve_alerts", "reject_alerts"]
    inlines = [UserAlertInline]

    fieldsets = [
        ("Basic Information", {"fields": ["title", "text", "shock_type", "data_source"]}),
        ("Timeline", {"fields": ["shock_date", "valid_from", "valid_until"]}),
        ("Classification", {"fields": ["severity", "go_no_go", "go_no_go_date"]}),
        ("Geographic Scope", {"fields": ["locations"]}),
        ("Metadata", {"fields": ["created_at", "updated_at", "is_active"], "classes": ["collapse"]}),
    ]

    filter_horizontal = ["locations"]

    def approve_alerts(self, request, queryset):
        """Admin action to approve selected alerts."""
        from django.utils import timezone
        updated = queryset.update(go_no_go=True, go_no_go_date=timezone.now())
        self.message_user(request, f"{updated} alert(s) approved successfully.")
    approve_alerts.short_description = "Approve selected alerts"

    def reject_alerts(self, request, queryset):
        """Admin action to reject selected alerts."""
        from django.utils import timezone
        updated = queryset.update(go_no_go=False, go_no_go_date=timezone.now())
        self.message_user(request, f"{updated} alert(s) rejected.")
    reject_alerts.short_description = "Reject selected alerts"


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin configuration for Subscription model."""

    list_display = ["user", "method", "frequency", "active", "location_count", "shock_type_count", "created_at"]
    list_filter = ["active", "method", "frequency", "created_at"]
    search_fields = ["user__username", "user__email", "user__first_name", "user__last_name"]
    readonly_fields = ["created_at", "updated_at"]
    actions = ["activate_subscriptions", "deactivate_subscriptions"]

    fieldsets = [
        ("User & Preferences", {"fields": ["user", "active", "method", "frequency"]}),
        ("Filters", {"fields": ["locations", "shock_types"]}),
        ("Metadata", {"fields": ["created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    filter_horizontal = ["locations", "shock_types"]

    def location_count(self, obj):
        """Display count of subscribed locations."""
        return obj.locations.count()

    location_count.short_description = "Locations"

    def shock_type_count(self, obj):
        """Display count of subscribed shock types."""
        return obj.shock_types.count()

    shock_type_count.short_description = "Shock Types"

    def activate_subscriptions(self, request, queryset):
        """Admin action to activate selected subscriptions."""
        updated = queryset.update(active=True)
        self.message_user(request, f"{updated} subscription(s) activated successfully.")
    activate_subscriptions.short_description = "Activate selected subscriptions"

    def deactivate_subscriptions(self, request, queryset):
        """Admin action to deactivate selected subscriptions."""
        updated = queryset.update(active=False)
        self.message_user(request, f"{updated} subscription(s) deactivated.")
    deactivate_subscriptions.short_description = "Deactivate selected subscriptions"


@admin.register(UserAlert)
class UserAlertAdmin(admin.ModelAdmin):
    """Admin configuration for UserAlert model."""

    list_display = ["user", "alert", "is_read", "rating", "bookmarked", "is_flagged", "received_at", "updated_at"]
    list_filter = ["bookmarked", "flag_false", "flag_incomplete", "rating", "received_at", "read_at"]
    search_fields = ["user__username", "user__email", "alert__title", "alert__title_en", "alert__title_ar", "comment"]
    readonly_fields = ["created_at", "updated_at", "is_read", "is_rated", "is_flagged"]

    fieldsets = [
        ("User & Alert", {"fields": ["user", "alert"]}),
        ("Engagement", {"fields": ["received_at", "read_at", "bookmarked"]}),
        ("Feedback", {"fields": ["rating", "rating_at", "flag_false", "flag_incomplete", "comment"]}),
        ("Metadata", {"fields": ["created_at", "updated_at", "is_read", "is_rated", "is_flagged"], "classes": ["collapse"]}),
    ]


@admin.register(EmailTemplate)
class EmailTemplateAdmin(TranslationAdmin):
    """Admin interface for email templates with live preview."""

    list_display = ['name', 'get_subject_short', 'active', 'updated_at']
    list_filter = ['active', 'name', 'created_at']
    readonly_fields = ['created_at', 'updated_at']
    search_fields = ['subject', 'subject_en', 'subject_ar', 'description']

    fieldsets = [
        ('Template Information', {
            'fields': ['name', 'description', 'active']
        }),
        ('Email Subject', {
            'fields': ['subject']
        }),
        ('HTML Template', {
            'fields': ['html_header', 'html_footer', 'html_wrapper'],
            'description': 'Use Django template syntax. Available variables: {{user}}, {{alert}}, {{unsubscribe_url}}, etc.'
        }),
        ('Plain Text Template', {
            'fields': ['text_header', 'text_footer', 'text_wrapper']
        }),
        ('Metadata', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    def get_subject_short(self, obj):
        """Return truncated subject for list display."""
        return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
    get_subject_short.short_description = 'Subject'

    def get_form(self, request, obj=None, **kwargs):
        """Customize form with better textarea widgets."""
        form = super().get_form(request, obj, **kwargs)

        # Make text areas larger
        textarea_fields = ['html_header', 'html_footer', 'html_wrapper', 'text_header', 'text_footer', 'text_wrapper']
        for field in textarea_fields:
            if field in form.base_fields:
                form.base_fields[field].widget = forms.Textarea(attrs={'rows': 10, 'cols': 80})

        return form

    def save_model(self, request, obj, form, change):
        """Custom save with logging."""
        super().save_model(request, obj, form, change)

        action = 'updated' if change else 'created'
        self.message_user(
            request,
            f"Email template '{obj.name}' has been {action}.",
            level='INFO'
        )
