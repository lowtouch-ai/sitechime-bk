from rest_framework import serializers
from .models import JsonData, TncAcceptance
from django.contrib.auth.models import User
from django.utils import timezone

class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'email']
        read_only_fields = ['id', 'username', 'email']

class JsonDataSerializer(serializers.ModelSerializer):
    """
    Serializer for the JsonData model
    """
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = JsonData
        fields = ['id', 'user', 'name', 'data', 'created_at', 'updated_at', 'uuid', 'is_public']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'uuid']
    
    def create(self, validated_data):
        """
        Create a new JsonData instance, setting the user from the request
        """
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)

class PublicJsonDataSerializer(serializers.ModelSerializer):
    """
    Serializer for publicly accessible JsonData
    """
    class Meta:
        model = JsonData
        fields = ['name', 'data', 'created_at', 'updated_at']
        read_only_fields = ['name', 'data', 'created_at', 'updated_at']

class TncAcceptanceSerializer(serializers.ModelSerializer):
    """
    Serializer for the TncAcceptance model
    """
    class Meta:
        model = TncAcceptance
        fields = ['id', 'config_id', 'ip_address', 'accepted_at', 'user_agent']
        read_only_fields = ['id', 'accepted_at']
        
    def create(self, validated_data):
        """
        Create a new TncAcceptance record
        If a record for this config_id and IP already exists, update the timestamp instead
        """
        config_id = validated_data.get('config_id')
        ip_address = validated_data.get('ip_address')
        
        # Try to get an existing record
        try:
            instance = TncAcceptance.objects.get(
                config_id=config_id, 
                ip_address=ip_address
            )
            # Update the timestamp and user agent
            instance.accepted_at = timezone.now()
            if 'user_agent' in validated_data:
                instance.user_agent = validated_data.get('user_agent')
            instance.save()
            return instance
        except TncAcceptance.DoesNotExist:
            # Create a new record
            return super().create(validated_data)
