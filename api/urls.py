from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JsonDataViewSet, OpenAIProxyView, public_json_data

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'json-data', JsonDataViewSet, basename='json-data')

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('rest_framework.urls')),
    # Public access to JsonData via UUID
    path('public/json-data/<uuid:uuid>/', public_json_data, name='public-json-data'),
    # OpenAI proxy endpoints
    path('openai/<path:path>', OpenAIProxyView.as_view(), name='openai-proxy'),
]
