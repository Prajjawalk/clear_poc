"""URL configuration for translation app."""

from django.urls import path

from . import views

app_name = "translation"

urlpatterns = [
    path("", views.translation_demo, name="demo"),
    path("coverage/", views.translation_coverage_view, name="coverage"),
    path("set-language/", views.set_language, name="set_language"),
    path("api/translate/", views.api_translate, name="api_translate"),
]
