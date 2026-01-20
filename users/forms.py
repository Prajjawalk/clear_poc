"""Forms for user management."""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import UserProfile


class UserProfileForm(forms.ModelForm):
    """Form for editing user profile."""

    class Meta:
        model = UserProfile
        fields = [
            'email_notifications_enabled',
            'preferred_language',
            'timezone',
        ]
        widgets = {
            'email_notifications_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'preferred_language': forms.Select(attrs={
                'class': 'form-select'
            }),
            'timezone': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
        help_texts = {
            'email_notifications_enabled': 'Enable this to receive email notifications for alerts matching your subscriptions.',
            'preferred_language': 'Choose your preferred language for email notifications.',
            'timezone': 'Your timezone for scheduling digest emails.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add email verification status info
        if self.instance and self.instance.pk:
            if not self.instance.email_verified:
                self.fields['email_notifications_enabled'].help_text = (
                    'You must verify your email address before enabling email notifications.'
                )
                self.fields['email_notifications_enabled'].widget.attrs['disabled'] = True


class UserCreateForm(UserCreationForm):
    """Form for creating new users with email."""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'user@example.com'
        }),
        help_text='Required. A verification email will be sent to this address.'
    )

    first_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First name'
        })
    )

    last_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last name'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Username'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add Bootstrap classes to password fields
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})

    def save(self, commit=True):
        """Save user and set email."""
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']

        if commit:
            user.save()

        return user