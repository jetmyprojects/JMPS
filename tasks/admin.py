from django.contrib import admin
from .models import Task

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('global_project_id', 'project_name', 'user', 'status', 'created_at')
    search_fields = ('project_name', 'user__username', 'user__email')
    list_filter = ('status', 'created_at')
    readonly_fields = ('userId', 'global_project_id')

    @admin.display(description='Global Project ID', ordering='id')
    def global_project_id(self, obj):
        return obj.id # Returns the database Primary Key
