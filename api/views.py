from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse
import json
import os

from rest_framework import viewsets, filters, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from revproxy.views import ProxyView
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

from .models import JsonData
from .serializers import JsonDataSerializer, PublicJsonDataSerializer
from utils.logger import api_logger, security_logger

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
        api_logger.debug(f"Fetching JsonData for user {user.username}")
        return JsonData.objects.filter(user=user)
    
    def perform_create(self, serializer):
        """Override perform_create to add logging"""
        instance = serializer.save(user=self.request.user)
        api_logger.info(f"JsonData created: {instance.name} by user {self.request.user.username}")
        return instance

    def perform_update(self, serializer):
        """Override perform_update to add logging"""
        instance = serializer.save()
        api_logger.info(f"JsonData updated: {instance.name} by user {self.request.user.username}")
        return instance

    def perform_destroy(self, instance):
        """Override perform_destroy to add logging"""
        name = instance.name
        api_logger.info(f"JsonData deleted: {name} by user {self.request.user.username}")
        instance.delete()
    
    @action(detail=False, methods=['get'])
    def names(self):
        """
        Return a list of all the unique names of JsonData for the current user.
        """
        names = self.get_queryset().values_list('name', flat=True).distinct()
        api_logger.debug(f"Retrieved {len(names)} unique names for user {self.request.user.username}")
        return Response(names)
    
    @action(detail=True, methods=['post'])
    def make_public(self, request, pk=None):
        """
        Make a JsonData instance publicly accessible via UUID
        """
        json_data = self.get_object()
        json_data.make_public()
        serializer = self.get_serializer(json_data)
        api_logger.info(f"JsonData made public: {json_data.name} (UUID: {json_data.uuid}) by user {request.user.username}")
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
        api_logger.info(f"JsonData made private: {json_data.name} by user {request.user.username}")
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
    api_logger.info(f"Public JsonData accessed: {json_data.name} (UUID: {uuid})")
    return Response(serializer.data)


class RateLimitedProxyView(ProxyView):
    """
    Base class for rate-limited proxy views
    """
    upstream = settings.OPENAI_PROXY_URL
    retries = 0
    add_remote_user = True
    stream = True  # Enable streaming responses
    
    @method_decorator(ratelimit(key='user', rate='1/m', method='POST'))
    def post(self, request, path):
        """
        Rate-limited POST requests
        """
        api_logger.debug(f"Rate-limited proxy request to path: {path}")
        return super().post(request, path)


class OpenAIProxyView(RateLimitedProxyView):
    """
    Proxy view for OpenAI API with rate limiting
    
    Can authenticate users via UUID of JsonData model by providing 
    the UUID in the 'X-JsonData-UUID' header or 'uuid' query parameter
    
    If BENCHMARK_MODE=1 is set in environment, returns static responses without making proxy calls
    """
    permission_classes = [permissions.AllowAny]
    timeout = 3000000  # Set timeout for upstream requests
    retries = 1  # Allow one retry
    chunk_size = 1024  # Optimal chunk size for streaming (8KB)
    
    def dispatch(self, request, *args, **kwargs):
        """
        Override dispatch to handle UUID authentication before processing the request
        """
        # Check if benchmark mode is enabled
        benchmark_mode = settings.BENCHMARK_MODE
        
        if benchmark_mode and request.method == 'POST':
            api_logger.info("Benchmark mode is enabled, returning static response")
            return self.get_benchmark_response(request, *args, **kwargs)
            
        # Try to authenticate via UUID
        uuid_value = request.headers.get('X-Config-Key') or request.GET.get('uuid')
        
        # Fallback: check Authorization header for the UUID if it's a Bearer token
        if not uuid_value:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                uuid_value = auth_header.split(' ')[1]

        # Add authorization token from settings
        token = settings.OPENWEBUI_API_TOKEN

        if token:
            request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'
            api_logger.debug(f"Authorization token added to request headers")

        
        if uuid_value:#remove this to enable uuid authentication
            try:
                # Find JsonData with the provided UUID and that is public
                json_data = JsonData.objects.get(uuid=uuid_value, is_public=True)
                
                # Attach the user to the request
                request.user = json_data.user
                
                # Log the authentication success
                security_logger.info(f"Successfully authenticated request as user {json_data.user.username} via JsonData UUID {uuid_value}")
                
            except (JsonData.DoesNotExist, ValueError):
                # If UUID is invalid or JsonData doesn't exist, log the failure
                security_logger.warning(f"Failed authentication attempt with UUID: {uuid_value}")
        
        # Continue with regular dispatch
        return super().dispatch(request, *args, **kwargs)
    
    def get_benchmark_response(self, request, *args, **kwargs):
        """
        Return a static response for benchmark mode
        """
        try:
            # Parse the request body to determine the response format
            request_body = json.loads(request.body)
            
            # Check if streaming is requested
            stream = request_body.get('stream', False)
            
            if stream:
                # Return a streaming response
                return StreamingHttpResponse(
                    self.benchmark_stream_generator(),
                    content_type='text/event-stream'
                )
            else:
                # Return a regular JSON response
                return Response({
                    "id": "chatcmpl-benchmark",
                    "object": "chat.completion",
                    "created": 123456789,
                    "model": "benchmark-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "This is a benchmark response from the proxy backend."
                            },
                            "finish_reason": "stop"
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 10,
                        "total_tokens": 20
                    }
                })
        except Exception as e:
            api_logger.error(f"Error generating benchmark response: {str(e)}")
            return Response(
                {"error": "Failed to generate benchmark response"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
    def benchmark_stream_generator(self):
        """
        Generator for benchmark streaming response
        """
        chunks = [
            "This ", "is ", "a ", "benchmark ", "streaming ", "response ", "from ", "the ", "proxy ", "backend."
        ]
        
        for i, chunk in enumerate(chunks):
            data = {
                "id": "chatcmpl-benchmark",
                "object": "chat.completion.chunk",
                "created": 123456789,
                "model": "benchmark-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": chunk
                        },
                        "finish_reason": None if i < len(chunks) - 1 else "stop"
                    }
                ]
            }
            yield f"data: {json.dumps(data)}\n\n"
            import time
            time.sleep(0.1)  # Simulate network delay
            
        yield "data: [DONE]\n\n"
    
    def get_proxy_request_headers(self, request):
        """
        Add any headers needed for the OpenAI compatible server
        """
        headers = super().get_proxy_request_headers(request)
        
        # Add headers for better streaming performance
        headers.update({
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Transfer-Encoding': 'chunked'
        })
        
        # Forward any external client-originated headers that are intended for
        # context propagation to the agent/upstream. These headers are expected
        # to be prefixed with X-LTAI-EXT- by convention and are whitelisted
        # (see settings.CORS_ALLOW_HEADERS).
        forwarded = []
        try:
            for hname, hval in request.headers.items():
                if hname.lower().startswith('x-ltai-ext-'):
                    # Add header as-is to upstream request
                    headers[hname] = hval
                    forwarded.append(hname)
        except Exception as e:
            api_logger.exception('Error while extracting X-LTAI-EXT headers: %s', e)

        if forwarded:
            # Log only the header names for auditing; do NOT log sensitive values
            security_logger.info(f"Forwarding external headers to upstream: {forwarded} for path {request.path}")

        api_logger.debug(f"Proxy request headers: {list(headers.keys())}")
        return headers
