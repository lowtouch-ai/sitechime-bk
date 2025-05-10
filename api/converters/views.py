"""
Views for JSON and YAML conversion endpoints.
"""
from django.http import HttpResponse
from django.core.cache import cache
import hashlib
import requests

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from utils.logger import api_logger
from utils.converters import json_to_yaml, yaml_to_json


@api_view(['GET'])
@permission_classes([AllowAny])
def convert_json_to_yaml(request):
    """
    API endpoint to convert JSON file to YAML format
    Requires a URL to a JSON file as a query parameter
    Returns the converted YAML as a downloadable file
    Results are cached for improved performance
    """
    # Get the URL from the query parameters
    url = request.GET.get('url')
    if not url:
        api_logger.warning(f"JSON to YAML conversion attempt without URL")
        return Response(
            {'error': 'URL is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Generate a cache key based on the URL
    cache_key = f"json_to_yaml_{hashlib.md5(url.encode()).hexdigest()}"
    
    # Check if the result is in cache
    cached_result = cache.get(cache_key)
    if cached_result:
        # Create a filename based on the original URL
        filename = url.split('/')[-1].split('.')[0] + '.yaml'
        
        # Create a response with the cached YAML data as a file
        file_response = HttpResponse(cached_result, content_type='application/x-yaml')
        file_response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        api_logger.info(f"JSON to YAML conversion served from cache for URL: {url}, sending as file: {filename}")
        return file_response
    
    try:
        # Fetch the content from the URL
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise exception for non-200 responses
        
        # Convert JSON to YAML
        yaml_data = json_to_yaml(response.text)
        
        # Store the result in cache for 1 hour (3600 seconds)
        cache.set(cache_key, yaml_data, 3600)
        
        # Create a filename based on the original URL
        filename = url.split('/')[-1].split('.')[0] + '.yaml'
        
        # Create a response with the YAML data as a file
        file_response = HttpResponse(yaml_data, content_type='application/x-yaml')
        file_response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        api_logger.info(f"JSON to YAML conversion successful for URL: {url}, sending as file: {filename}")
        return file_response
    except requests.RequestException as e:
        api_logger.error(f"Error fetching JSON from URL {url}: {str(e)}")
        return Response(
            {'error': f'Error fetching JSON from URL: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except ValueError as e:
        api_logger.error(f"Error converting JSON to YAML: {str(e)}")
        return Response(
            {'error': f'Error converting JSON to YAML: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        api_logger.error(f"Unexpected error in JSON to YAML conversion: {str(e)}")
        return Response(
            {'error': 'An unexpected error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def convert_yaml_to_json(request):
    """
    API endpoint to convert YAML file to JSON format
    Requires a URL to a YAML file as a query parameter
    Returns the converted JSON as a downloadable file
    Results are cached for improved performance
    """
    # Get the URL from the query parameters
    url = request.GET.get('url')
    if not url:
        api_logger.warning(f"YAML to JSON conversion attempt without URL")
        return Response(
            {'error': 'URL is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Generate a cache key based on the URL
    cache_key = f"yaml_to_json_{hashlib.md5(url.encode()).hexdigest()}"
    
    # Check if the result is in cache
    cached_result = cache.get(cache_key)
    if cached_result:
        # Create a filename based on the original URL
        filename = url.split('/')[-1].split('.')[0] + '.json'
        
        # Create a response with the cached JSON data as a file
        file_response = HttpResponse(cached_result, content_type='application/json')
        file_response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        api_logger.info(f"YAML to JSON conversion served from cache for URL: {url}, sending as file: {filename}")
        return file_response
    
    try:
        # Fetch the content from the URL
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise exception for non-200 responses
        
        # Convert YAML to JSON
        json_data = yaml_to_json(response.text)
        
        # Store the result in cache for 1 hour (3600 seconds)
        cache.set(cache_key, json_data, 3600)
        
        # Create a filename based on the original URL
        filename = url.split('/')[-1].split('.')[0] + '.json'
        
        # Create a response with the JSON data as a file
        file_response = HttpResponse(json_data, content_type='application/json')
        file_response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        api_logger.info(f"YAML to JSON conversion successful for URL: {url}, sending as file: {filename}")
        return file_response
    except requests.RequestException as e:
        api_logger.error(f"Error fetching YAML from URL {url}: {str(e)}")
        return Response(
            {'error': f'Error fetching YAML from URL: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except ValueError as e:
        api_logger.error(f"Error converting YAML to JSON: {str(e)}")
        return Response(
            {'error': f'Error converting YAML to JSON: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        api_logger.error(f"Unexpected error in YAML to JSON conversion: {str(e)}")
        return Response(
            {'error': 'An unexpected error occurred'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
