"""Template tags for translation app."""

from typing import Any

from django import template
from django.template.base import FilterExpression, Parser, Token
from django.template.context import Context
from django.utils.safestring import mark_safe

from ..utils import (
    get_available_languages,
    get_current_language_info,
    get_language_switch_url,
)
from ..utils import (
    translate as translate_func,
)

register = template.Library()


@register.simple_tag
def translate(label: str, **kwargs) -> str:
    """
    Simple template tag to translate a label.

    Usage:
        {% translate "welcome_message" %}
        {% translate "hello_user" name="John" %}
    """
    return translate_func(label, **kwargs)


@register.simple_tag(takes_context=True)
def translate_safe(context: Context, label: str, **kwargs) -> str:
    """
    Template tag that marks the output as safe HTML.

    Usage:
        {% translate_safe "html_message" %}
        {% translate_safe "greeting" name=user.name %}
    """
    result = translate_func(label, **kwargs)
    return mark_safe(result)


class TranslateNode(template.Node):
    """Custom template node for advanced translate functionality."""

    def __init__(self, label_expr: FilterExpression, kwargs_expressions: dict[str, FilterExpression]):
        """Initialize the translate node."""
        self.label_expr = label_expr
        self.kwargs_expressions = kwargs_expressions

    def render(self, context: Context) -> str:
        """Render the translation."""
        try:
            label = self.label_expr.resolve(context)
            kwargs = {}

            for key, expr in self.kwargs_expressions.items():
                kwargs[key] = expr.resolve(context)

            return translate_func(label, **kwargs)
        except Exception:
            # Graceful fallback
            try:
                return self.label_expr.resolve(context)
            except Exception:
                return ""


@register.tag
def trans(parser: Parser, token: Token) -> TranslateNode:
    """
    Advanced template tag with support for variable resolution.

    Usage:
        {% trans label_variable %}
        {% trans "static_label" %}
        {% trans label_var name=user.name count=items|length %}
    """
    bits = token.split_contents()
    if len(bits) < 2:
        raise template.TemplateSyntaxError(f"'{bits[0]}' tag requires at least one argument (the label)")

    label_expr = parser.compile_filter(bits[1])
    kwargs_expressions = {}

    # Parse keyword arguments
    for bit in bits[2:]:
        if "=" not in bit:
            raise template.TemplateSyntaxError(f"'{bits[0]}' tag arguments must be in key=value format")

        key, value = bit.split("=", 1)
        kwargs_expressions[key] = parser.compile_filter(value)

    return TranslateNode(label_expr, kwargs_expressions)


@register.filter
def t(value: str) -> str:
    """
    Simple filter for translation.

    Usage:
        {{ "welcome_message"|t }}
        {{ label_variable|t }}
    """
    return translate_func(value)


@register.inclusion_tag("translation/debug_info.html", takes_context=True)
def translation_debug_info(context: Context, label: str) -> dict[str, Any]:
    """
    Inclusion tag to show debug information about a translation.

    Usage:
        {% translation_debug_info "welcome_message" %}
    """
    from django.conf import settings

    debug_info = {
        "label": label,
        "translation": translate_func(label),
        "show_debug": settings.DEBUG,
        "current_language": context.get("LANGUAGE_CODE", "en"),
    }

    # Add coverage info if available
    try:
        from ..utils import get_translation_coverage

        debug_info["coverage"] = get_translation_coverage()
    except Exception:
        debug_info["coverage"] = {}

    return debug_info


@register.simple_tag
def translation_coverage() -> dict[str, Any]:
    """
    Template tag to get translation coverage statistics.

    Usage:
        {% translation_coverage as coverage %}
        {% for lang, info in coverage.items %}
            {{ info.name }}: {{ info.percentage }}%
        {% endfor %}
    """
    try:
        from ..utils import get_translation_coverage

        return get_translation_coverage()
    except Exception:
        return {}


@register.simple_tag
def available_languages() -> list:
    """
    Template tag to get available languages.

    Usage:
        {% available_languages as languages %}
        {% for code, name in languages %}
            <option value="{{ code }}">{{ name }}</option>
        {% endfor %}
    """
    return get_available_languages()


@register.simple_tag
def current_language() -> dict[str, Any]:
    """
    Template tag to get current language information.

    Usage:
        {% current_language as lang_info %}
        Current language: {{ lang_info.name }} ({{ lang_info.code }})
        Direction: {{ lang_info.direction }}
    """
    return get_current_language_info()


@register.simple_tag(takes_context=True)
def language_switch_url(context: Context, language_code: str) -> str:
    """
    Template tag to generate language switch URL.

    Usage:
        <a href="{% language_switch_url 'fr' %}">Français</a>
        <a href="{% language_switch_url lang_code %}">{{ lang_name }}</a>
    """
    request = context.get("request")
    current_path = request.get_full_path() if request else None
    return get_language_switch_url(language_code, current_path)


@register.inclusion_tag("translation/language_switcher.html", takes_context=True)
def language_switcher(context: Context, style: str = "dropdown") -> dict[str, Any]:
    """
    Inclusion tag to render a language switcher component.

    Usage:
        {% language_switcher %}
        {% language_switcher style="pills" %}
        {% language_switcher style="flags" %}
    """
    request = context.get("request")
    current_path = request.get_full_path() if request else None
    current_lang = get_current_language_info()
    available_langs = get_available_languages()

    # Generate switch URLs for each language
    switch_urls = {}
    for code, _name in available_langs:
        switch_urls[code] = get_language_switch_url(code, current_path)

    return {
        "current_language": current_lang,
        "available_languages": available_langs,
        "switch_urls": switch_urls,
        "style": style,
        "request": request,
    }


@register.filter
def language_name(language_code: str) -> str:
    """
    Filter to get language name from code.

    Usage:
        {{ "fr"|language_name }}  -> "French"
        {{ current_lang_code|language_name }}
    """
    for code, name in get_available_languages():
        if code == language_code:
            return name
    return language_code


@register.filter
def dict_get(dictionary: dict, key: str) -> Any:
    """
    Filter to get dictionary value by key.

    Usage:
        {{ my_dict|dict_get:"key" }}
        {{ switch_urls|dict_get:lang_code }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key, "")
    return ""


@register.filter
def language_flag(language_code: str) -> str:
    """
    Filter to get country code for flag display.

    Usage:
        {{ "en"|language_flag }}  -> "gb"
        {{ "fr"|language_flag }}  -> "fr"
    """
    # Map language codes to country codes for flag images
    flag_mapping = {
        "en": "gb",  # English -> UK flag (Great Britain)
        "fr": "fr",  # French -> France flag
        "es": "es",  # Spanish -> Spain flag
        "de": "de",  # German -> Germany flag
        "it": "it",  # Italian -> Italy flag
        "pt": "pt",  # Portuguese -> Portugal flag
        "ru": "ru",  # Russian -> Russia flag
        "zh": "cn",  # Chinese -> China flag
        "ja": "jp",  # Japanese -> Japan flag
        "ko": "kr",  # Korean -> South Korea flag
        "ar": "sa",  # Arabic -> Saudi Arabia flag
    }

    return flag_mapping.get(language_code.lower(), language_code.lower())
