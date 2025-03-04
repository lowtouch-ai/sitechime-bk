from django.shortcuts import render
from django.conf import settings
from django.http import HttpResponse

from rest_framework import viewsets, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from revproxy.views import ProxyView
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

from .models import JsonData
from .serializers import JsonDataSerializer

# Create your views here.
class JsonDataViewSet(viewsets.ModelViewSet):
    """
    ViewSet for viewing and editing JSON data.
    
    This viewset automatically provides `list`, `create`, `retrieve`,
    `update` and `destroy` actions.
    """
    serializer_class = JsonDataSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at', 'updated_at']
    
    def get_queryset(self):
        """
        This view should return a list of all JsonData
        for the currently authenticated user.
        """
        user = self.request.user
        return JsonData.objects.filter(user=user)
    
    @action(detail=False, methods=['get'])
    def names(self):
        """
        Return a list of all the unique names of JsonData for the current user.
        """
        names = self.get_queryset().values_list('name', flat=True).distinct()
        return Response(names)


class RateLimitedProxyView(ProxyView):
    """
    Base class for rate-limited proxy views
    """
    upstream = settings.OPENAI_PROXY_URL
    retries = 0
    add_remote_user = True
    
    @method_decorator(ratelimit(key='user', rate='60/m', method='POST'))
    def post(self, request, path):
        """
        Rate-limited POST requests
        """
        return super().post(request, path)


class OpenAIProxyView(RateLimitedProxyView):
    """
    Proxy view for OpenAI API with rate limiting
    """
    def get_proxy_request_headers(self, request):
        """
        Add any headers needed for the OpenAI compatible server
        """
        headers = super().get_proxy_request_headers(request)
        # You can add any additional headers needed for your OpenAI compatible server here
        return headers
