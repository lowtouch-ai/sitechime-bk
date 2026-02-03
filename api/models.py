from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json
import uuid

# Create your models here.
class JsonData(models.Model):
    """
    Model to store JSON data associated with users.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='json_data')
    name = models.CharField(max_length=255, help_text="Name/identifier for this JSON data")
    data = models.JSONField(help_text="JSON data stored by the user")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, 
                           help_text="UUID for public access to this data")
    is_public = models.BooleanField(default=False, 
                                   help_text="Whether this data is publicly accessible via UUID")
    
    class Meta:
        verbose_name = "JSON Data"
        verbose_name_plural = "JSON Data"
        ordering = ['-updated_at']
        unique_together = ['user', 'name']
    
    def __str__(self):
        return self.name
