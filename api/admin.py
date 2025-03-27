from django.contrib import admin
from .models import JsonData, TncAcceptance

# Register your models here.
@admin.register(JsonData)
class JsonDataAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at', 'updated_at')
    list_filter = ('user', 'created_at', 'updated_at')
    search_fields = ('name', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('user', 'name')
        }),
        ('Data', {
            'fields': ('data',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(TncAcceptance)
class TncAcceptanceAdmin(admin.ModelAdmin):
    list_display = ('config_id', 'ip_address', 'accepted_at', 'truncated_user_agent')
    list_filter = ('accepted_at', 'config_id')
    search_fields = ('config_id', 'ip_address')
    readonly_fields = ('accepted_at',)
    
    def truncated_user_agent(self, obj):
        """Display truncated user agent in the admin list view"""
        if obj.user_agent and len(obj.user_agent) > 50:
            return f"{obj.user_agent[:50]}..."
        return obj.user_agent
    
    truncated_user_agent.short_description = 'User Agent'
