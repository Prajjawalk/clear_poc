"""User management models."""

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """Extended user profile with notification preferences."""

    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('ar', 'العربية'),
    ]

    TIMEZONE_CHOICES = [
        ('Africa/Khartoum', 'Sudan (Khartoum)'),
        ('UTC', 'UTC'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    # Email preferences
    email_notifications_enabled = models.BooleanField(
        default=False,  # Safeguard against accidental spamming
        help_text="Master switch for email notifications - must be explicitly enabled"
    )
    email_verified = models.BooleanField(
        default=False,
        help_text="Whether the user's email has been verified"
    )
    email_verification_token = models.CharField(
        max_length=100,
        blank=True,
        help_text="Token for email verification"
    )
    email_verification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When verification email was last sent"
    )

    # Preferences
    preferred_language = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
        default='en',
        help_text="User's preferred language for communications"
    )
    timezone = models.CharField(
        max_length=50,
        choices=TIMEZONE_CHOICES,
        default='Africa/Khartoum',
        help_text="User's timezone for scheduling notifications"
    )

    # Metadata
    last_login_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of last login"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__username']
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.username} Profile"

    @property
    def can_receive_emails(self):
        """Check if user can receive email notifications."""
        return (
            self.email_notifications_enabled and
            self.email_verified and
            self.user.email
        )

    def generate_verification_token(self):
        """Generate a new email verification token."""
        import secrets
        self.email_verification_token = secrets.token_urlsafe(32)
        self.save(update_fields=['email_verification_token'])
        return self.email_verification_token


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when a new User is created."""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved."""
    if hasattr(instance, 'profile'):
        instance.profile.save()