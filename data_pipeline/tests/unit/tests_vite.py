"""Tests for Vite template tags."""

from django.template import Context, Template
from django.test import TestCase


class ViteTemplateTagsTests(TestCase):
    """Test Vite template tags functionality."""

    def test_vite_css_tag(self):
        """Test that vite_css tag generates correct CSS link."""
        template = Template('{% load vite_tags %}{% vite_css %}')
        rendered = template.render(Context({}))

        # Should contain a link tag with the hashed CSS file
        self.assertIn('<link rel="stylesheet"', rendered)
        self.assertIn('style.', rendered)  # Should include the hash
        self.assertIn('.css', rendered)

    def test_vite_js_tag(self):
        """Test that vite_js tag generates correct JS script tag."""
        template = Template('{% load vite_tags %}{% vite_js %}')
        rendered = template.render(Context({}))

        # Should contain a script tag with the hashed JS file
        self.assertIn('<script type="module"', rendered)
        self.assertIn('main.', rendered)  # Should include the hash
        self.assertIn('.js', rendered)

    def test_vite_legacy_js_tag(self):
        """Test that vite_legacy_js tag generates correct legacy JS."""
        template = Template('{% load vite_tags %}{% vite_legacy_js %}')
        rendered = template.render(Context({}))

        # Should contain a script tag with nomodule for legacy browsers
        self.assertIn('<script nomodule', rendered)
        self.assertIn('main-legacy.', rendered)  # Should include the hash

    def test_vite_asset_tag(self):
        """Test that vite_asset tag returns correct asset URL."""
        template = Template('{% load vite_tags %}{% vite_asset "scss/main.scss" %}')
        rendered = template.render(Context({}))

        # Should return a static URL path
        self.assertIn('/static/dist/', rendered)
        self.assertIn('.css', rendered)
