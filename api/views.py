from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.http import HttpResponse

from rest_framework import viewsets, filters, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from revproxy.views import ProxyView
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

from .models import JsonData, TncAcceptance
from .serializers import JsonDataSerializer, PublicJsonDataSerializer, TncAcceptanceSerializer
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
    """
    permission_classes = [permissions.AllowAny]
    timeout = 30  # Set timeout for upstream requests
    retries = 1  # Allow one retry
    chunk_size = 32  # Optimal chunk size for streaming (8KB)
    
    def dispatch(self, request, *args, **kwargs):
        """
        Override dispatch to handle UUID authentication before processing the request
        """
        # Try to authenticate via UUID
        uuid_value = request.headers.get('X-Config-Key') or request.GET.get('uuid')
        
        if uuid_value:
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
        
        api_logger.debug(f"Proxy request headers: {headers}")
        return headers


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def accept_tnc(request):
    """
    API endpoint for recording Terms and Conditions acceptance
    Requires config_id in request data
    Automatically captures IP address from the request
    """
    # Get client IP address
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')
    
    # Add IP address to request data
    data = request.data.copy()
    data['ip_address'] = ip_address
    
    # Get user agent if available
    user_agent = request.META.get('HTTP_USER_AGENT')
    if user_agent:
        data['user_agent'] = user_agent
    
    # Validate and save
    serializer = TncAcceptanceSerializer(data=data)
    if serializer.is_valid():
        instance = serializer.save()
        api_logger.info(f"Terms and Conditions accepted for config_id {instance.config_id} from IP {ip_address}")
        return Response(
            {'message': 'Terms and Conditions acceptance recorded successfully'},
            status=status.HTTP_201_CREATED
        )
    api_logger.warning(f"Invalid T&C acceptance attempt from IP {ip_address}: {serializer.errors}")
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def check_tnc_acceptance(request, config_id):
    """
    API endpoint to check if the current IP has accepted Terms and Conditions for a given config_id
    """
    # Get client IP address
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0]
    else:
        ip_address = request.META.get('REMOTE_ADDR')
    
    # Check if a record exists
    try:
        tnc_acceptance = TncAcceptance.objects.get(
            config_id=config_id,
            ip_address=ip_address
        )
        api_logger.debug(f"T&C acceptance found for config_id {config_id} from IP {ip_address}")
        return Response({
            'accepted': True,
            'accepted_at': tnc_acceptance.accepted_at
        })
    except TncAcceptance.DoesNotExist:
        api_logger.debug(f"No T&C acceptance found for config_id {config_id} from IP {ip_address}")
        return Response({
            'accepted': False
        })


class TncAcceptanceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for administrators to view and manage TncAcceptance records
    """
    queryset = TncAcceptance.objects.all()
    serializer_class = TncAcceptanceSerializer
    permission_classes = [permissions.IsAdminUser]  # Only admins can access this
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['config_id', 'ip_address']
    ordering_fields = ['config_id', 'ip_address', 'accepted_at']
    
    def list(self, request, *args, **kwargs):
        """Override list to add logging"""
        response = super().list(request, *args, **kwargs)
        api_logger.info(f"TncAcceptance records listed by admin user {request.user.username}")
        return response

    def perform_destroy(self, instance):
        """Override perform_destroy to add logging"""
        api_logger.info(f"TncAcceptance record deleted by admin {self.request.user.username}: config_id={instance.config_id}, ip={instance.ip_address}")
        instance.delete()
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Return statistics about TnC acceptances
        """
        total_acceptances = TncAcceptance.objects.count()
        unique_configs = TncAcceptance.objects.values('config_id').distinct().count()
        unique_ips = TncAcceptance.objects.values('ip_address').distinct().count()
        
        api_logger.info(f"TncAcceptance stats retrieved by admin {request.user.username}")
        return Response({
            'total_acceptances': total_acceptances,
            'unique_configs': unique_configs,
            'unique_ips': unique_ips
        })
