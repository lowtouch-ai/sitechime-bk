from rest_framework import serializers
from .models import JsonData
from django.contrib.auth.models import User

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
        fields = ['id', 'user', 'name', 'data', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        """
        Create a new JsonData instance, setting the user from the request
        """
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)
