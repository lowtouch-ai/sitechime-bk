from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.http import HttpResponse

from rest_framework import viewsets, filters, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from revproxy.views import ProxyView
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

from .models import JsonData
from .serializers import JsonDataSerializer, PublicJsonDataSerializer

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
    
    @action(detail=True, methods=['post'])
    def make_public(self, request, pk=None):
        """
        Make a JsonData instance publicly accessible via UUID
        """
        json_data = self.get_object()
        json_data.make_public()
        serializer = self.get_serializer(json_data)
        return Response({
            'status': 'success',
            'message': f'Data is now publicly accessible via UUID: {json_data.uuid}',
            'data': serializer.data
        })
    
    @action(detail=True, methods=['post'])
    def make_private(self, request, pk=None):
        """
        Make a JsonData instance private (not accessible via UUID)
        """
        json_data = self.get_object()
        json_data.make_private()
        serializer = self.get_serializer(json_data)
        return Response({
            'status': 'success',
            'message': 'Data is now private',
            'data': serializer.data
        })


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def public_json_data(request, uuid):
    """
    View for accessing publicly shared JsonData via UUID
    """
    json_data = get_object_or_404(JsonData, uuid=uuid, is_public=True)
    serializer = PublicJsonDataSerializer(json_data)
    return Response(serializer.data)


class RateLimitedProxyView(ProxyView):
    """
    Base class for rate-limited proxy views
    """
    upstream = settings.OPENAI_PROXY_URL
    retries = 0
    add_remote_user = True
    
    @method_decorator(ratelimit(key='user', rate='1/m', method='POST'))
    def post(self, request, path):
        """
        Rate-limited POST requests
        """
        return super().post(request, path)


class OpenAIProxyView(RateLimitedProxyView):
    """
    Proxy view for OpenAI API with rate limiting
    
    Can authenticate users via UUID of JsonData model by providing 
    the UUID in the 'X-JsonData-UUID' header or 'uuid' query parameter
    """
    permission_classes = [permissions.AllowAny]
    
    def dispatch(self, request, *args, **kwargs):
        """
        Override dispatch to handle UUID authentication before processing the request
        """
        # Try to authenticate via UUID
        uuid_value = request.headers.get('X-JsonData-UUID') or request.GET.get('uuid')
        
        if uuid_value:
            try:
                # Find JsonData with the provided UUID and that is public
                json_data = JsonData.objects.get(uuid=uuid_value, is_public=True)
                
                # Attach the user to the request
                request.user = json_data.user
                
                # Log the authentication success
                print(f"Authenticated request as user {json_data.user.username} via JsonData UUID")
                
            except (JsonData.DoesNotExist, ValueError):
                # If UUID is invalid or JsonData doesn't exist, continue with default authentication
                print("Failed to authenticate via UUID")
                pass
                
        # Continue with regular dispatch
        return super().dispatch(request, *args, **kwargs)
    
    def get_proxy_request_headers(self, request):
        """
        Add any headers needed for the OpenAI compatible server
        """
        headers = super().get_proxy_request_headers(request)

        print("Headers before modification:", headers)

        # You can add any additional headers needed for your OpenAI compatible server here
        return headers
