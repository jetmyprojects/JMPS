from rest_framework import serializers
from .models import Task, TaskFile
from django.utils import timezone
import datetime
import mimetypes
from storage.utils import can_upload
try:
    from subscriptions.models import UserSubscription
except ImportError:
    # Handle potential circular import if it ever arises, though unlikely here
    UserSubscription = None

class TaskFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskFile
        fields = ['id', 'file', 'uploaded_at']

class TaskSerializer(serializers.ModelSerializer):
    # Fix 1: Use standard ID field, do not map to userId
    id = serializers.IntegerField(read_only=True)
    project_id = serializers.IntegerField(source='userId', read_only=True)
    files = TaskFileSerializer(many=True, read_only=True)
    uploaded_files = serializers.ListField(
        child=serializers.FileField(max_length=100000, allow_empty_file=False, use_url=False),
        write_only=True,
        required=False
    )

    class Meta:
        model = Task
        fields = ['id', 'project_id', 'user', 'project_name', 'deadline_date', 'deadline_time', 'project_notes', 'status', 'previous_status', 'is_pinned', 'created_at', 'updated_at', 'files', 'uploaded_files']
        read_only_fields = ['user', 'created_at', 'updated_at', 'files', 'previous_status']

    def validate(self, data):
        deadline_date = data.get('deadline_date')
        deadline_time = data.get('deadline_time')

        # Get effective date and time (from data or instance)
        effective_date = deadline_date
        effective_time = deadline_time

        if self.instance:
            if effective_date is None:
                effective_date = self.instance.deadline_date
            if effective_time is None:
                effective_time = self.instance.deadline_time
        
        # Validation
        if effective_date:
            # Get current local date and time based on User's Timezone
            user = self.context['request'].user
            import pytz
            
            # Default to server time (usually UTC)
            target_tz = timezone.get_current_timezone()
            
            # If user has a preference, use it
            if user.is_authenticated and hasattr(user, 'timezone') and user.timezone:
                try:
                    target_tz = pytz.timezone(user.timezone)
                except pytz.UnknownTimeZoneError:
                    pass
            
            now_local = timezone.now().astimezone(target_tz)
            today_local = now_local.date()
            now_time_local = now_local.time()

            # Check if date is in the past
            if effective_date < today_local:
                 # Allow if updating and the date hasn't changed
                 if not (self.instance and self.instance.deadline_date == effective_date):
                      raise serializers.ValidationError({"deadline_date": "The deadline date cannot be in the past."})

            # Check time if date is today (either explicitly or implicitly)
            if effective_date == today_local:
                # We care if checking time is relevant.
                # If time is being updated (deadline_time is in data)
                if deadline_time:
                     if deadline_time < now_time_local:
                         raise serializers.ValidationError({"deadline_time": "The deadline time cannot be in the past."})
        

        # Storage Limit Validation
        uploaded_files = data.get('uploaded_files', [])
        print(uploaded_files)
        if uploaded_files:
            # Check for invalid file types (.exe, etc.)
            for file_obj in uploaded_files:
                print(file_obj)
                # Fix 2: Stronger File Type Validation
                import os
                ext = os.path.splitext(file_obj.name)[1].lower()
                allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg', '.docx', '.pptx', '.txt']
                if ext not in allowed_extensions:
                     raise serializers.ValidationError(
                        f"Unsupported file type: {ext}. Allowed types are: pdf, png, jpg, docx, pptx, txt."
                    )

                # --- VIRUS SCANNER IMPLEMENTATION ---
                from services.security.virus_scanner import scan_uploaded_file
                
                if not scan_uploaded_file(file_obj):
                     raise serializers.ValidationError(
                        f"SECURITY ALERT: Virus detected in '{file_obj.name}'. Upload rejected."
                    )
                # ------------------------------------

            user = self.context['request'].user
            
            # Check file count limit (Max 5)
            current_file_count = 0
            if self.instance:
                 current_file_count = self.instance.files.count()
            
            if (current_file_count + len(uploaded_files)) > 5:
                 raise serializers.ValidationError(f"You can only upload a maximum of 5 files. You currently have {current_file_count} files.")

            # Calculate total size of new files
            new_total_size = sum(f.size for f in uploaded_files)
            
            # Storage Limit Validation using centralized helper
            if not can_upload(user, new_total_size):
                # Retrieve limit for creating a nice message
                limit_mb = 100 # Default
                if UserSubscription:
                    try:
                        sub = UserSubscription.objects.get(user=user, is_active=True)
                        limit_mb = sub.plan.storage_limit_mb if sub.plan else 100
                    except UserSubscription.DoesNotExist:
                        limit_mb = 100
                    
                raise serializers.ValidationError(
                    f"Storage limit exceeded. This upload would exceed your {limit_mb} MB limit. Please upgrade your plan."
                )

        return data

    def validate_project_name(self, value):
        from django.utils.html import strip_tags
        if strip_tags(value) != value:
            raise serializers.ValidationError("HTML content is not allowed in project name.")
        return value

    def validate_project_notes(self, value):
        from django.utils.html import strip_tags
        if value and strip_tags(value) != value:
             raise serializers.ValidationError("HTML content is not allowed in project notes.")
        return value


    def create(self, validated_data):
        uploaded_files = validated_data.pop('uploaded_files', [])
        task = Task.objects.create(**validated_data)
        for file in uploaded_files:
            TaskFile.objects.create(task=task, file=file)
        return task

    def update(self, instance, validated_data):
        uploaded_files = validated_data.pop('uploaded_files', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        for file in uploaded_files:
            TaskFile.objects.create(task=instance, file=file)
        return instance
