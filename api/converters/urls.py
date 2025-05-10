"""
URL configuration for converter endpoints.
"""
from django.urls import path
from .views import convert_json_to_yaml, convert_yaml_to_json

urlpatterns = [
    path('json-to-yaml/', convert_json_to_yaml, name='convert-json-to-yaml'),
    path('yaml-to-json/', convert_yaml_to_json, name='convert-yaml-to-json'),
]
