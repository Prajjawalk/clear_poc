"""Management command to create default email templates."""

from django.core.management.base import BaseCommand

from alerts.models import EmailTemplate


class Command(BaseCommand):
    """Create default email templates in the database."""

    help = "Create default email templates for notifications"

    def add_arguments(self, parser):
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing templates instead of creating new ones',
        )
        parser.add_argument(
            '--template',
            type=str,
            help='Create only a specific template by name',
        )

    def handle(self, *args, **options):
        update = options['update']
        template_filter = options['template']

        templates_data = [
            {
                'name': 'individual_alert',
                'description': 'Template for individual alert notifications',
                'subject': '[EWAS Alert] {{alert.title}}',
                'html_header': '''
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .header { background-color: #dc3545; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background-color: #f8f9fa; }
        .alert-info { background-color: white; padding: 15px; border-radius: 5px; margin: 15px 0; }
        .footer { padding: 20px; text-align: center; font-size: 12px; color: #6c757d; }
        .btn { background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>EWAS Sudan Alert System</h1>
        </div>
        <div class="content">
            <h2>{{alert.shock_type.name}} Alert</h2>
            <p>Dear {{user.first_name|default:"Subscriber"}},</p>
            <p>A new alert has been issued that matches your subscription preferences:</p>
            <div class="alert-info">
                <h3>{{alert.title}}</h3>
                <p><strong>Date:</strong> {{alert.shock_date}}</p>
                <p><strong>Severity:</strong> {{alert.severity_display}}</p>
                <p><strong>Locations:</strong> {% for location in alert.locations.all %}{{location.name}}{% if not forloop.last %}, {% endif %}{% endfor %}</p>
                <div>{{alert.text}}</div>
            </div>
            <p><a href="{{site_url}}/alerts/alert/{{alert.id}}/" class="btn">View Full Alert</a></p>
        </div>
                ''',
                'html_footer': '''
        <div class="footer">
            <hr>
            <p>You received this email because you subscribed to alerts for this region and type.</p>
            <p><a href="{{unsubscribe_url}}">Unsubscribe</a> | <a href="{{settings_url}}">Update Preferences</a></p>
        </div>
    </div>
</body>
</html>
                ''',
                'text_header': '''
EWAS Sudan Alert System

{{alert.shock_type.name}} Alert

Dear {{user.first_name|default:"Subscriber"}},

A new alert has been issued that matches your subscription preferences:

Title: {{alert.title}}
Date: {{alert.shock_date}}
Severity: {{alert.severity_display}}
Locations: {% for location in alert.locations.all %}{{location.name}}{% if not forloop.last %}, {% endif %}{% endfor %}

{{alert.text}}

View full alert: {{site_url}}/alerts/alert/{{alert.id}}/
                ''',
                'text_footer': '''

---
You received this email because you subscribed to alerts for this region and type.
Unsubscribe: {{unsubscribe_url}}
Update Preferences: {{settings_url}}
                '''
            },
            {
                'name': 'daily_digest',
                'description': 'Daily digest of alerts',
                'subject': '[EWAS] Daily Alert Digest - {{alerts|length}} alert{{alerts|length|pluralize}}',
                'html_header': '''
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .header { background-color: #28a745; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; }
        .alert-item { border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }
        .footer { padding: 20px; text-align: center; font-size: 12px; color: #6c757d; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Daily Alert Digest</h1>
        </div>
        <div class="content">
            <p>Dear {{user.first_name|default:"Subscriber"}},</p>
            <p>Here are the alerts from the last 24 hours that match your subscriptions:</p>
            {% for alert in alerts %}
            <div class="alert-item">
                <h3>{{alert.title}}</h3>
                <p><strong>Type:</strong> {{alert.shock_type.name}} | <strong>Severity:</strong> {{alert.severity_display}}</p>
                <p>{{alert.text|truncatewords:30}}</p>
                <p><a href="{{site_url}}/alerts/alert/{{alert.id}}/">Read more</a></p>
            </div>
            {% endfor %}
        </div>
                ''',
                'html_footer': '''
        <div class="footer">
            <hr>
            <p><a href="{{unsubscribe_url}}">Unsubscribe</a> | <a href="{{settings_url}}">Update Preferences</a></p>
        </div>
    </div>
</body>
</html>
                ''',
                'text_header': '''
EWAS Sudan - Daily Alert Digest

Dear {{user.first_name|default:"Subscriber"}},

Here are the alerts from the last 24 hours that match your subscriptions:

{% for alert in alerts %}
{{forloop.counter}}. {{alert.title}}
   Type: {{alert.shock_type.name}} | Severity: {{alert.severity_display}}
   {{alert.text|truncatewords:30}}
   View: {{site_url}}/alerts/alert/{{alert.id}}/

{% endfor %}
                ''',
                'text_footer': '''
---
Unsubscribe: {{unsubscribe_url}}
Update Preferences: {{settings_url}}
                '''
            },
            {
                'name': 'email_verification',
                'description': 'Email verification template',
                'subject': '[EWAS] Verify your email address',
                'html_header': '''
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .header { background-color: #007bff; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; }
        .btn { background-color: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; }
        .footer { padding: 20px; text-align: center; font-size: 12px; color: #6c757d; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Email Verification</h1>
        </div>
        <div class="content">
            <p>Dear {{user.first_name|default:user.username}},</p>
            <p>Thank you for registering with EWAS Sudan Alert System.</p>
            <p>Please click the button below to verify your email address and enable email notifications:</p>
            <p style="text-align: center; margin: 30px 0;">
                <a href="{{verification_url}}" class="btn">Verify Email Address</a>
            </p>
            <p>If the button doesn't work, copy and paste this link into your browser:</p>
            <p>{{verification_url}}</p>
        </div>
                ''',
                'html_footer': '''
        <div class="footer">
            <p>If you didn't request this verification, please ignore this email.</p>
        </div>
    </div>
</body>
</html>
                ''',
                'text_header': '''
EWAS Sudan - Email Verification

Dear {{user.first_name|default:user.username}},

Thank you for registering with EWAS Sudan Alert System.

Please verify your email address by clicking the link below:
{{verification_url}}
                ''',
                'text_footer': '''

If you didn't request this verification, please ignore this email.
                '''
            }
        ]

        # Filter templates if requested
        if template_filter:
            templates_data = [t for t in templates_data if t['name'] == template_filter]
            if not templates_data:
                self.stdout.write(
                    self.style.ERROR(f"Template '{template_filter}' not found")
                )
                return

        created_count = 0
        updated_count = 0

        for template_data in templates_data:
            name = template_data['name']

            if update:
                template, created = EmailTemplate.objects.update_or_create(
                    name=name,
                    defaults=template_data
                )
                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"Created template: {name}")
                    )
                else:
                    updated_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"Updated template: {name}")
                    )
            else:
                template, created = EmailTemplate.objects.get_or_create(
                    name=name,
                    defaults=template_data
                )
                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"Created template: {name}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"Template already exists: {name}")
                    )

        if update:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Template operation completed: {created_count} created, {updated_count} updated"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Created {created_count} new templates")
            )