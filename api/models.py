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
        return f"{self.name} ({self.user.username})"
    
    def set_data(self, data_dict):
        """
        Set the JSON data from a Python dictionary
        """
        self.data = data_dict
        
    def get_data(self):
        """
        Get the JSON data as a Python dictionary
        """
        return self.data
    
    def make_public(self):
        """
        Make this data publicly accessible via UUID
        """
        self.is_public = True
        self.save()
    
    def make_private(self):
        """
        Make this data private (not accessible via UUID)
        """
        self.is_public = False
        self.save()

class TncAcceptance(models.Model):
    """
    Model to track Terms and Conditions acceptance by config ID and IP address.
    """
    config_id = models.CharField(max_length=255, help_text="Configuration ID associated with the TnC")
    ip_address = models.GenericIPAddressField(help_text="IP address of the user who accepted the TnC")
    accepted_at = models.DateTimeField(default=timezone.now)
    user_agent = models.TextField(blank=True, null=True, help_text="User agent of the browser/client")
    
    class Meta:
        verbose_name = "TnC Acceptance"
        verbose_name_plural = "TnC Acceptances"
        ordering = ['-accepted_at']
    
    def __str__(self):
        return f"TnC Acceptance: {self.config_id} from {self.ip_address} at {self.accepted_at}"
