from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JsonDataViewSet, OpenAIProxyView

# Create a router and register our viewsets with it
router = DefaultRouter()
router.register(r'json-data', JsonDataViewSet, basename='json-data')

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('rest_framework.urls')),
    # OpenAI proxy endpoints
    path('openai/<path:path>', OpenAIProxyView.as_view(), name='openai-proxy'),
]
