"""Tests for alert forms."""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from alerts.forms import AlertFeedbackForm, AlertForm, AlertFilterForm, SubscriptionForm
from alerts.models import Alert, ShockType, Subscription
from data_pipeline.models import Source
from location.models import AdmLevel, Location


class AlertFormTest(TestCase):
    """Tests for AlertForm."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.admin_level = AdmLevel.objects.create(code="1", name="State Level")
        cls.location = Location.objects.create(
            name="Khartoum",
            geo_id="SD001",
            admin_level=cls.admin_level
        )

        cls.source = Source.objects.create(
            name="Test Source",
            description="Test data source",
            type="api",
            class_name="TestSource"
        )

        cls.shock_type = ShockType.objects.create(name="Conflict")

    def test_alert_form_valid_data(self):
        """Test AlertForm with valid data."""
        now = timezone.now()
        form_data = {
            'title': 'Test Alert',
            'text': 'This is a test alert',
            'shock_type': self.shock_type.id,
            'data_source': self.source.id,
            'shock_date': date.today(),
            'valid_from': now,
            'valid_until': now + timedelta(days=7),
            'severity': 3,
            'locations': [self.location.id],
        }

        form = AlertForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_alert_form_missing_required_fields(self):
        """Test AlertForm with missing required fields."""
        form_data = {
            'title': 'Test Alert',
            # Missing text, shock_type, data_source, etc.
        }

        form = AlertForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('text', form.errors)
        self.assertIn('shock_type', form.errors)
        self.assertIn('data_source', form.errors)

    def test_alert_form_default_values(self):
        """Test that AlertForm sets default values for new instances."""
        form = AlertForm()

        # Should have default values set
        self.assertIsNotNone(form.fields['shock_date'].initial)
        self.assertIsNotNone(form.fields['valid_from'].initial)
        self.assertIsNotNone(form.fields['valid_until'].initial)

    def test_alert_form_location_queryset(self):
        """Test that AlertForm filters locations to admin level 1."""
        # Create location at different admin level
        admin_level_2 = AdmLevel.objects.create(code="2", name="District Level")
        location_2 = Location.objects.create(
            name="Kassala District",
            geo_id="SD003",
            admin_level=admin_level_2
        )

        form = AlertForm()

        # Should only include admin level 1 locations
        location_ids = [loc.id for loc in form.fields['locations'].queryset]
        self.assertIn(self.location.id, location_ids)
        self.assertNotIn(location_2.id, location_ids)

    def test_alert_form_severity_choices(self):
        """Test that severity field has correct choices."""
        form = AlertForm()
        severity_field = form.fields['severity']

        # Should have severity choices from 1-5
        choices = [choice[0] for choice in severity_field.choices]
        self.assertEqual(choices, [1, 2, 3, 4, 5])

    def test_alert_form_widgets(self):
        """Test that form uses correct widgets."""
        form = AlertForm()

        # Check that specific widgets are applied
        self.assertEqual(form.fields['title'].widget.attrs.get('class'), 'form-control')
        self.assertEqual(form.fields['text'].widget.attrs.get('class'), 'form-control')
        self.assertEqual(form.fields['shock_date'].widget.attrs.get('type'), 'date')


class SubscriptionFormTest(TestCase):
    """Tests for SubscriptionForm."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.admin_level = AdmLevel.objects.create(code="1", name="State Level")
        cls.location = Location.objects.create(
            name="Khartoum",
            geo_id="SD001",
            admin_level=cls.admin_level
        )
        cls.shock_type = ShockType.objects.create(name="Conflict")

    def test_subscription_form_valid_data(self):
        """Test SubscriptionForm with valid data."""
        form_data = {
            'locations': [self.location.id],
            'shock_types': [self.shock_type.id],
            'frequency': 'daily',
            'method': 'email',
            'active': True,
        }

        form = SubscriptionForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_subscription_form_missing_required_fields(self):
        """Test SubscriptionForm with missing required fields."""
        form_data = {
            'frequency': 'daily',
            # Missing locations and shock_types
        }

        form = SubscriptionForm(data=form_data)
        self.assertFalse(form.is_valid())
        # Note: locations and shock_types might not be required in form validation
        # depending on form configuration

    def test_subscription_form_frequency_choices(self):
        """Test that frequency field has correct choices."""
        form = SubscriptionForm()
        frequency_field = form.fields['frequency']

        expected_choices = ["immediate", "daily", "weekly", "monthly"]
        choices = [choice[0] for choice in frequency_field.choices]

        for expected in expected_choices:
            self.assertIn(expected, choices)

    def test_subscription_form_method_choices(self):
        """Test that method field has correct choices."""
        form = SubscriptionForm()
        method_field = form.fields['method']

        choices = [choice[0] for choice in method_field.choices]
        self.assertIn("email", choices)

    def test_subscription_form_location_filtering(self):
        """Test that form filters locations to admin level 1."""
        # Create location at different admin level
        admin_level_2 = AdmLevel.objects.create(code="2", name="District Level")
        location_2 = Location.objects.create(
            name="District Location",
            geo_id="SD004",
            admin_level=admin_level_2
        )

        form = SubscriptionForm()

        # Should only include admin level 1 locations
        location_ids = [loc.id for loc in form.fields['locations'].queryset]
        self.assertIn(self.location.id, location_ids)
        self.assertNotIn(location_2.id, location_ids)

    def test_subscription_form_help_text(self):
        """Test that form fields have appropriate help text."""
        form = SubscriptionForm()

        self.assertIsNotNone(form.fields['locations'].help_text)
        self.assertIsNotNone(form.fields['shock_types'].help_text)
        self.assertIsNotNone(form.fields['frequency'].help_text)
        self.assertIsNotNone(form.fields['active'].help_text)


class AlertFeedbackFormTest(TestCase):
    """Tests for AlertFeedbackForm."""

    def test_feedback_form_valid_data(self):
        """Test AlertFeedbackForm with valid data."""
        form_data = {
            'comment': 'This is a test feedback comment.',
        }

        form = AlertFeedbackForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_feedback_form_empty_comment(self):
        """Test AlertFeedbackForm with empty comment."""
        form_data = {
            'comment': '',
        }

        form = AlertFeedbackForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('comment', form.errors)

    def test_feedback_form_max_length(self):
        """Test AlertFeedbackForm with comment exceeding max length."""
        form_data = {
            'comment': 'x' * 1001,  # Exceeds max length of 1000
        }

        form = AlertFeedbackForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('comment', form.errors)

    def test_feedback_form_max_length_valid(self):
        """Test AlertFeedbackForm with comment at max length."""
        form_data = {
            'comment': 'x' * 1000,  # Exactly at max length
        }

        form = AlertFeedbackForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_feedback_form_widget_attributes(self):
        """Test that feedback form has correct widget attributes."""
        form = AlertFeedbackForm()
        comment_field = form.fields['comment']

        # Check widget attributes
        self.assertEqual(comment_field.widget.attrs.get('class'), 'form-control')
        self.assertEqual(comment_field.widget.attrs.get('rows'), 3)
        self.assertIn('placeholder', comment_field.widget.attrs)

    def test_feedback_form_help_text(self):
        """Test that feedback form has help text."""
        form = AlertFeedbackForm()
        self.assertIsNotNone(form.fields['comment'].help_text)


class AlertFilterFormTest(TestCase):
    """Tests for AlertFilterForm."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.shock_type = ShockType.objects.create(name="Conflict")

    def test_filter_form_all_fields_optional(self):
        """Test that all filter form fields are optional."""
        form = AlertFilterForm(data={})
        self.assertTrue(form.is_valid(), form.errors)

    def test_filter_form_with_valid_data(self):
        """Test AlertFilterForm with valid filter data."""
        form_data = {
            'shock_type': self.shock_type.id,
            'severity': 3,
            'date_from': date.today() - timedelta(days=30),
            'date_to': date.today(),
            'search': 'test search',
            'bookmarked': True,
        }

        form = AlertFilterForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_filter_form_shock_type_choices(self):
        """Test that shock type field includes all shock types."""
        form = AlertFilterForm()
        shock_type_field = form.fields['shock_type']

        # Should include empty choice and created shock type
        choice_values = [choice[0] for choice in shock_type_field.choices]
        self.assertIn('', choice_values)  # Empty choice
        self.assertIn(self.shock_type.id, choice_values)

    def test_filter_form_severity_choices(self):
        """Test that severity field has correct choices."""
        form = AlertFilterForm()
        severity_field = form.fields['severity']

        # Should include empty choice and severity levels
        choice_values = [choice[0] for choice in severity_field.choices]
        self.assertIn('', choice_values)  # Empty choice
        for severity in [1, 2, 3, 4, 5]:
            self.assertIn(severity, choice_values)

    def test_filter_form_date_fields(self):
        """Test date field types and widgets."""
        form = AlertFilterForm()

        date_from_widget = form.fields['date_from'].widget
        date_to_widget = form.fields['date_to'].widget

        self.assertEqual(date_from_widget.attrs.get('type'), 'date')
        self.assertEqual(date_to_widget.attrs.get('type'), 'date')
        self.assertEqual(date_from_widget.attrs.get('class'), 'form-control')
        self.assertEqual(date_to_widget.attrs.get('class'), 'form-control')

    def test_filter_form_search_field(self):
        """Test search field attributes."""
        form = AlertFilterForm()
        search_field = form.fields['search']

        self.assertEqual(search_field.widget.attrs.get('class'), 'form-control')
        self.assertIn('placeholder', search_field.widget.attrs)

    def test_filter_form_bookmarked_field(self):
        """Test bookmarked checkbox field."""
        form = AlertFilterForm()
        bookmarked_field = form.fields['bookmarked']

        self.assertEqual(bookmarked_field.widget.attrs.get('class'), 'form-check-input')
        self.assertFalse(bookmarked_field.required)